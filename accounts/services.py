"""Bulk student upload: parse -> validate -> report -> (admin confirms) -> create (AUTH-02..05)."""
import csv
import io
import re
import secrets
import string

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from academics.models import SchoolClass
from core.models import audit
from .hashers import InitialPasswordHasher
from .models import BulkUploadBatch, User

TEMPLATE_COLUMNS = ["first name", "last name", "index number", "class or form", "stream"]


def _norm_header(h):
    return re.sub(r"\s+", " ", str(h or "").replace("_", " ").strip().lower())


def parse_upload(uploaded_file):
    """Return a list of dicts keyed by normalised header. Supports .csv and .xlsx."""
    name = (uploaded_file.name or "").lower()
    raw = uploaded_file.read()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(raw), read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
    elif name.endswith(".csv"):
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    else:
        raise ValueError("Please upload the template as an .xlsx or .csv file.")
    if not rows:
        raise ValueError("The file is empty.")
    headers = [_norm_header(h) for h in rows[0]]
    missing = [c for c in TEMPLATE_COLUMNS[:4] if c not in headers]
    if missing:
        raise ValueError("Missing column(s): " + ", ".join(missing) + ". Please use the downloadable template.")
    out = []
    for i, r in enumerate(rows[1:], start=2):  # spreadsheet row number
        if r is None or all(c in (None, "") for c in r):
            continue
        d = {h: ("" if v is None else str(v).strip()) for h, v in zip(headers, r)}
        d["_row"] = i
        out.append(d)
    return out


def validate_rows(rows):
    existing_index = set(User.objects.exclude(index_number="").values_list("index_number", flat=True))
    seen = {}
    clean, errors = [], []
    for d in rows:
        problems = []
        first, last = d.get("first name", ""), d.get("last name", "")
        index, klass, stream = d.get("index number", ""), d.get("class or form", ""), d.get("stream", "")
        for label, val in (("first name", first), ("last name", last), ("index number", index), ("class or form", klass)):
            if not val:
                problems.append(f"missing {label}")
        if index:
            if index in seen:
                problems.append(f"duplicate index number (also on row {seen[index]})")
            elif index in existing_index:
                problems.append("index number already registered")
            seen.setdefault(index, d["_row"])
        if klass and not re.search(r"[1-4]", klass):
            problems.append("class or form must include a form number from 1 to 4")
        if problems:
            errors.append({"row": d["_row"], "problems": problems})
        else:
            clean.append({"first_name": first, "last_name": last, "index_number": index, "class": klass, "stream": stream})
    report = {"total_rows": len(rows), "valid_rows": len(clean), "invalid_rows": len(errors), "errors": errors}
    return clean, report


def make_username(first_name, taken):
    """Exact first name, lowercase, no spaces; amina, amina2, amina3 ... (AUTH-04)."""
    base = re.sub(r"\s+", "", first_name.strip().lower()) or "student"
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}{n}"
    taken.add(candidate)
    return candidate


@transaction.atomic
def create_students(batch, actor):
    taken = set(User.objects.values_list("username", flat=True))
    class_cache = {}
    users = []
    for r in batch.rows:
        key = (r["class"], r["stream"])
        if key not in class_cache:
            level = int(re.search(r"[1-4]", r["class"]).group())
            class_cache[key], _ = SchoolClass.objects.get_or_create(
                name=r["class"], stream=r["stream"], defaults={"form_level": level}
            )
        users.append(
            User(
                username=make_username(r["first_name"], taken),
                first_name=r["first_name"],
                last_name=r["last_name"],
                index_number=r["index_number"],
                school_class=class_cache[key],
                role=User.Role.STUDENT,
                must_change_password=True,
                # Starting password = index number, stored hashed, never plain (AUTH-05).
                password=make_password(r["index_number"], hasher=InitialPasswordHasher.algorithm),
            )
        )
    User.objects.bulk_create(users)
    ids = list(User.objects.filter(username__in=[u.username for u in users]).values_list("pk", flat=True))
    batch.status = BulkUploadBatch.CONFIRMED
    batch.created_user_ids = ids
    batch.rows = []  # no need to keep the data once accounts exist
    batch.save()
    audit(actor, "students.bulk_upload", batch.pk, created=len(ids))
    return ids


def validate_staff_password(password, user=None):
    """AUTH-07: teacher and admin accounts need strong passwords. Raises DjangoValidationError."""
    problems = []
    if len(password) < 10:
        problems.append("Use at least 10 characters.")
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password)):
        problems.append("Use upper-case and lower-case letters and at least one number.")
    try:
        validate_password(password, user)
    except DjangoValidationError as e:
        problems += e.messages
    if problems:
        raise DjangoValidationError(problems)


def generate_password(length=12):
    """Random temporary password that always passes validate_staff_password."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw
