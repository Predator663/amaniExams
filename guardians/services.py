"""Parents: file upload, linking, and queuing the SMS that carry each student's login details."""
import csv
import io
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.authtoken.models import Token

from accounts.models import User
from . import crypto
from .models import Guardian, GuardianLink, SmsConfig, SmsJob
from .phones import mask, normalize_phone

TEMPLATE_COLUMNS = ["parent_name", "phone", "relationship", "student_index", "whatsapp", "language"]
ALIASES = {
    "parent_name": "parent_name", "name": "parent_name", "parent": "parent_name", "guardian": "parent_name", "guardian_name": "parent_name",
    "phone": "phone", "phone_number": "phone", "mobile": "phone", "simu": "phone", "telephone": "phone",
    "relationship": "relationship", "relation": "relationship",
    "student_index": "student_index", "index": "student_index", "index_number": "student_index", "student": "student_index", "students": "student_index",
    "whatsapp": "whatsapp", "has_whatsapp": "whatsapp", "language": "language", "lang": "language",
}
MAX_ROWS = 3000
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i, so it can be read from an SMS
MAX_ATTEMPTS = 3
LEASE_MINUTES = 10
NOTE_MAX = 160  # the optional custom line an administrator may add to every message
_GSM_BASIC = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM_EXT = set("^{}\\[~]|€")
_PUNCT = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " "}


# ------------------------------------------------------------------ reading the file
def parse_file(f):
    """Return a list of dicts using the template column names. Accepts .csv and .xlsx."""
    name = (getattr(f, "name", "") or "").lower()
    if name.endswith(".xlsx"):
        ws = load_workbook(f, read_only=True, data_only=True).active
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    elif name.endswith(".csv") or name.endswith(".txt"):
        text = f.read().decode("utf-8-sig", errors="replace")
        table = list(csv.reader(io.StringIO(text)))
    else:
        raise ValueError("Please upload the template as .csv or .xlsx.")
    table = [r for r in table if any(str(c or "").strip() for c in r)]
    if not table:
        raise ValueError("The file is empty.")
    head = [ALIASES.get(re.sub(r"[\s\-]+", "_", str(h or "").strip().lower())) for h in table[0]]
    if "phone" not in head or "student_index" not in head:
        raise ValueError("The first row must have the columns: parent_name, phone, relationship, student_index, whatsapp, language.")
    if len(table) - 1 > MAX_ROWS:
        raise ValueError(f"Please upload at most {MAX_ROWS} rows at a time.")
    rows = []
    for n, r in enumerate(table[1:], start=2):
        d = {"_row": n}
        for key, val in zip(head, r):
            if key and key not in d:
                d[key] = val
        rows.append(d)
    return rows


def _yes(v):
    return str(v or "").strip().lower() in ("yes", "y", "true", "1", "ndio", "x")


def _clean_name(v):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f<>]", " ", str(v or ""))).strip()[:120]


def split_indexes(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return [x for x in re.split(r"[,;/\s]+", str(v or "").strip()) if x]


def student_lookup():
    qs = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False).exclude(index_number="").select_related("school_class")
    out = {}
    for u in qs:
        out.setdefault(u.index_number.strip().lower(), u)
    return out


def validate_rows(rows):
    """Check every row. Nothing is saved. Returns (clean_rows, report)."""
    students = student_lookup()
    clean, report_rows, seen_phone = [], [], {}
    for d in rows:
        problems, warns = [], []
        name = _clean_name(d.get("parent_name"))
        phone = normalize_phone(d.get("phone"))
        if not name:
            problems.append("Parent name is missing.")
        if not phone:
            problems.append("Phone number is not a valid Tanzanian mobile number.")
        found, unknown = [], []
        idx = split_indexes(d.get("student_index"))
        if not idx:
            problems.append("Student index number is missing.")
        for i in idx:
            u = students.get(i.lower())
            (found if u else unknown).append(u or i)
        if unknown:
            problems.append("No active student with index number: " + ", ".join(unknown) + ".")
        lang = str(d.get("language") or "").strip().lower()[:2]
        if lang and lang not in ("sw", "en"):
            warns.append("Language should be sw or en; Kiswahili will be used.")
        if phone and phone in seen_phone:
            warns.append(f"Same phone as row {seen_phone[phone]}; the children are joined to one parent.")
        elif phone:
            seen_phone[phone] = d["_row"]
        status = "error" if problems else ("warn" if warns else "ok")
        report_rows.append({"row": d["_row"], "name": name, "phone": mask(phone) if phone else str(d.get("phone") or ""),
                            "students": [f"{u.first_name} {u.last_name} ({u.index_number})" for u in found],
                            "status": status, "problems": problems + warns})
        if not problems:
            clean.append({"name": name, "phone": phone, "relationship": _clean_name(d.get("relationship"))[:30],
                          "student_ids": [u.pk for u in found], "whatsapp": _yes(d.get("whatsapp")),
                          "language": lang if lang in ("sw", "en") else "sw"})
    phones = {c["phone"] for c in clean}
    existing = set(Guardian.objects.filter(phone_idx__in=[crypto.blind_index(p) for p in phones]).values_list("phone_idx", flat=True))
    new_links = 0
    for c in clean:
        g_exists = crypto.blind_index(c["phone"]) in existing
        gid = Guardian.objects.filter(phone_idx=crypto.blind_index(c["phone"])).values_list("pk", flat=True).first() if g_exists else None
        for sid in c["student_ids"]:
            if not (gid and GuardianLink.objects.filter(guardian_id=gid, student_id=sid).exists()):
                new_links += 1
    report = {"rows": report_rows, "total_rows": len(rows), "valid_rows": len(clean), "invalid_rows": len(rows) - len(clean),
              "parents_new": len(phones) - len(existing), "parents_existing": len(existing), "links_new": new_links}
    return clean, report


@transaction.atomic
def commit_rows(clean, user):
    created = updated = links = 0
    for c in clean:
        g = Guardian.objects.filter(phone_idx=crypto.blind_index(c["phone"])).first()
        if g is None:
            g = Guardian(created_by=user, relationship=c["relationship"], has_whatsapp=c["whatsapp"], language=c["language"])
            g.set_name(c["name"])
            g.set_phone(c["phone"])
            g.save()
            created += 1
        else:
            changed = False
            if c["whatsapp"] and not g.has_whatsapp:
                g.has_whatsapp, changed = True, True
            if c["relationship"] and not g.relationship:
                g.relationship, changed = c["relationship"], True
            if changed:
                g.save()
                updated += 1
        for sid in c["student_ids"]:
            _, made = GuardianLink.objects.get_or_create(guardian=g, student_id=sid)
            links += made
    return {"parents_created": created, "parents_updated": updated, "links_created": links}


# ------------------------------------------------------------------ the optional custom line
def clean_note(v):
    """The administrator's optional extra line: one line of plain text. Curly quotes and dashes (what phones and Word type) become
    plain ones so the SMS stays cheap, control characters and line breaks become spaces, extra spaces are squeezed."""
    v = "".join(_PUNCT.get(c, c) for c in str(v or ""))
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>]", " ", v)).strip()


def sms_parts(text):
    """(number of SMS the text will use, True if it has characters outside the cheap GSM alphabet, e.g. emoji)."""
    if all(c in _GSM_BASIC or c in _GSM_EXT for c in text):
        n = sum(2 if c in _GSM_EXT else 1 for c in text)
        return (1 if n <= 160 else -(-n // 153)), False
    n = len(text.encode("utf-16-le")) // 2
    return (1 if n <= 70 else -(-n // 67)), True


# ------------------------------------------------------------------ the message
def new_password():
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))


def build_body(lang, cfg, pairs, note=""):
    """pairs = [(student display name, username, password)]; note = the optional custom line. Plain characters only, to keep it cheap (GSM-7)."""
    url = (cfg.public_url or "").strip() or "the school website"
    school = "Amani Girls"
    if lang == "en":
        lines = [f"{school}: exam login. Open {url}"]
        lines += [f"{n}: user {u}, password {p}" for n, u, p in pairs]
        lines.append("Set a new password at first login. Do not share.")
    else:
        lines = [f"{school}: taarifa za kuingia kwenye mitihani. Fungua {url}"]
        lines += [f"{n}: jina {u}, nenosiri {p}" for n, u, p in pairs]
        lines.append("Weka nenosiri jipya ukiingia mara ya kwanza. Usimpe mtu.")
    if note:
        lines.append(note)  # the administrator's own line goes last, after the security reminder
    return "\n".join(lines)


def preview(items, cfg, note=""):
    """What a message will look like (first parent in the list, with a placeholder instead of a real password), and how many SMS it uses."""
    if not items:
        return {"text": "", "parts": 0, "unicode": False}
    g, kids = items[0]
    text = build_body(g.language, cfg, [(_display(s), s.username, "xxxxxxxx") for s in kids], note)
    parts, uni = sms_parts(text)
    return {"text": text, "parts": parts, "unicode": uni}


def _display(u):
    return f"{u.first_name} {u.last_name}".strip() or u.username


def plan_send(scope="all", class_id=None, guardian_ids=None, resend=False):
    """Decide who gets a message. Returns (items, skipped) and changes nothing.
    items = [(guardian, [students])]. A student gets credentials only while she has not yet changed her password
    (unless resend), and not if a message for her is already queued or sent (unless resend)."""
    gq = Guardian.objects.all().prefetch_related("links__student__school_class")
    if scope == "selected":
        gq = gq.filter(pk__in=guardian_ids or [])
    skipped = {"already_logged_in": 0, "already_sent": 0, "no_children": 0, "inactive": 0}
    busy = {}
    for j in SmsJob.objects.filter(status__in=SmsJob.OPEN + SmsJob.DONE).only("students", "status"):
        for sid in j.students:
            busy[sid] = j.status
    items = []
    for g in gq:
        kids = []
        for link in g.links.all():
            s = link.student
            if not (s.is_active and not s.is_archived):
                skipped["inactive"] += 1
            elif scope == "class" and str(s.school_class_id) != str(class_id):
                continue
            elif not resend and not s.must_change_password:
                skipped["already_logged_in"] += 1
            elif not resend and s.pk in busy:
                skipped["already_sent"] += 1
            else:
                kids.append(s)
        if kids:
            items.append((g, kids))
        elif not g.links.exists():
            skipped["no_children"] += 1
    return items, skipped


@transaction.atomic
def queue_send(items, user, note=""):
    """Give each listed student a fresh random password and queue ONE message per parent."""
    cfg = SmsConfig.load()
    jobs, passwords = 0, {}  # a student with two parents gets ONE password, so both messages work
    for g, kids in items:
        pairs = []
        for s in kids:
            if s.pk not in passwords:
                passwords[s.pk] = new_password()
                s.set_password(passwords[s.pk])
                s.must_change_password = True
                s.save(update_fields=["password", "must_change_password"])
                Token.objects.filter(user=s).delete()  # any old login stops working
            pairs.append((_display(s), s.username, passwords[s.pk]))
        SmsJob.objects.create(
            guardian=g, students=[s.pk for s in kids], to_enc=g.phone_enc,
            body_enc=crypto.encrypt(build_body(g.language, cfg, pairs, note)), note=note,
            summary=("Login details for " + ", ".join(p[0] for p in pairs))[:200], created_by=user)
        jobs += 1
    return jobs


@transaction.atomic
def requeue(job, user=None):
    """Try a failed message again. If its text was already erased (it had been sent), make a new one with new passwords."""
    if job.status not in (SmsJob.FAILED, SmsJob.CANCELLED):
        return False
    if not job.body_enc or job.status == SmsJob.CANCELLED:
        kids = list(User.objects.filter(pk__in=job.students, role=User.Role.STUDENT, is_active=True))
        if not kids or not job.guardian:
            return False
        cfg, pairs = SmsConfig.load(), []
        for s in kids:
            pw = new_password()
            s.set_password(pw)
            s.must_change_password = True
            s.save(update_fields=["password", "must_change_password"])
            Token.objects.filter(user=s).delete()
            pairs.append((_display(s), s.username, pw))
        job.body_enc = crypto.encrypt(build_body(job.guardian.language, cfg, pairs, job.note))
    job.status, job.attempts, job.error, job.leased_until, job.device = SmsJob.QUEUED, 0, "", None, None
    job.save()
    return True


# ------------------------------------------------------------------ the phone
def lease_jobs(device, limit):
    now = timezone.now()
    SmsJob.objects.filter(status=SmsJob.SENDING, leased_until__lt=now, attempts__gte=MAX_ATTEMPTS).update(
        status=SmsJob.FAILED, error="The phone did not confirm sending.")
    out = []
    with transaction.atomic():
        qs = SmsJob.objects.select_for_update().filter(
            Q(status=SmsJob.QUEUED) | Q(status=SmsJob.SENDING, leased_until__lt=now, attempts__lt=MAX_ATTEMPTS))
        for j in qs.order_by("id")[:limit]:
            j.status, j.device, j.attempts = SmsJob.SENDING, device, j.attempts + 1
            j.leased_until = now + timedelta(minutes=LEASE_MINUTES)
            j.save(update_fields=["status", "device", "attempts", "leased_until"])
            out.append({"id": j.pk, "to": crypto.decrypt(j.to_enc), "body": crypto.decrypt(j.body_enc)})
    return out


def apply_report(device, job_id, status, error=""):
    j = SmsJob.objects.filter(pk=job_id).first()
    if j is None or (j.device_id and j.device_id != device.pk):
        return False
    now = timezone.now()
    if status == "sent" and j.status in (SmsJob.SENDING, SmsJob.QUEUED, SmsJob.FAILED):
        j.status, j.sent_at, j.error, j.body_enc, j.leased_until = SmsJob.SENT, now, "", "", None  # erase the passwords
    elif status == "delivered" and j.status in (SmsJob.SENT, SmsJob.SENDING, SmsJob.DELIVERED):
        j.status, j.delivered_at, j.body_enc, j.leased_until = SmsJob.DELIVERED, now, "", None
        j.sent_at = j.sent_at or now
    elif status == "failed" and j.status in (SmsJob.SENDING, SmsJob.QUEUED, SmsJob.SENT):
        j.status, j.error, j.leased_until = SmsJob.FAILED, (error or "The phone could not send it.")[:200], None
    else:
        return False
    j.save()
    return True
