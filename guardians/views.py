import csv
import hashlib
import secrets
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsAdminRole
from core.models import audit
from core.pagination import paginate, page_params, wants_page
from . import crypto, services
from .models import Guardian, GuardianLink, SmsConfig, SmsDevice, SmsJob
from .phones import mask, normalize_phone

PAGE = 50
ONLINE_SECONDS = 90


def _kid(link):
    s = link.student
    return {"id": s.pk, "name": f"{s.first_name} {s.last_name}".strip() or s.username, "index": s.index_number,
            "class": str(s.school_class) if s.school_class_id else "", "logged_in": not s.must_change_password}


def _row(g, last):
    return {"id": g.pk, "name": g.name, "phone": mask(g.phone), "relationship": g.relationship, "has_whatsapp": g.has_whatsapp,
            "language": g.language, "children": [_kid(l) for l in g.links.all()],
            "last_message": {"status": last.status, "at": (last.sent_at or last.created_at)} if last else None}


def _err(msg, code=400):
    return Response({"detail": msg}, status=code)


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def guardians(request):
    """GET: list (search with q, filter with class, page with offset). POST: add one parent by hand."""
    if request.method == "POST":
        d = request.data
        rows = [{"_row": 1, "parent_name": d.get("name"), "phone": d.get("phone"), "relationship": d.get("relationship"),
                 "student_index": d.get("student_index"), "whatsapp": "yes" if d.get("has_whatsapp") else "", "language": d.get("language")}]
        clean, report = services.validate_rows(rows)
        if not clean:
            return Response({"detail": "; ".join(report["rows"][0]["problems"]) or "Check the details."}, status=400)
        out = services.commit_rows(clean, request.user)
        audit(request.user, "guardian.add", 1)
        return Response(out, status=201)
    p = request.query_params
    qs = Guardian.objects.prefetch_related("links__student__school_class").order_by("-id")
    if p.get("class"):
        qs = qs.filter(links__student__school_class_id=p["class"]).distinct()
    q = (p.get("q") or "").strip().lower()
    digits = "".join(c for c in q if c.isdigit())
    if digits.startswith("0"):
        digits = digits[1:]  # people type 0712..., the stored number is +255712...
    items = list(qs)
    if q:
        def hit(g):
            kids = " ".join(f"{l.student.first_name} {l.student.last_name} {l.student.index_number}" for l in g.links.all()).lower()
            return q in g.name.lower() or q in kids or (len(digits) >= 4 and digits in g.phone)
        items = [g for g in items if hit(g)]
    total = len(items)
    size, meta = PAGE, {}
    if wants_page(request):
        pg, size = page_params(request, PAGE)
        pages = max(1, -(-total // size))
        pg = min(pg, pages)
        offset = (pg - 1) * size
        meta = {"count": total, "page": pg, "pages": pages, "page_size": size}
    else:
        try:
            offset = max(0, int(p.get("offset", 0)))
        except ValueError:
            offset = 0
    page = items[offset:offset + size]
    last = {}
    for j in SmsJob.objects.filter(guardian__in=[g.pk for g in page]).order_by("id"):
        last[j.guardian_id] = j
    return Response({"total": total, "offset": offset, **meta, "results": [_row(g, last.get(g.pk)) for g in page]})


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def guardian_detail(request, pk):
    g = Guardian.objects.filter(pk=pk).first()
    if not g:
        return _err("Not found.", 404)
    if request.method == "DELETE":
        g.delete()
        audit(request.user, "guardian.delete", pk)
        return Response(status=204)
    d = request.data
    if "name" in d:
        name = services._clean_name(d["name"])
        if not name:
            return _err("The name cannot be empty.")
        g.set_name(name)
    if "phone" in d:
        phone = normalize_phone(d["phone"])
        if not phone:
            return _err("That is not a valid Tanzanian mobile number.")
        other = Guardian.objects.filter(phone_idx=crypto.blind_index(phone)).exclude(pk=g.pk).exists()
        if other:
            return _err("Another parent already has this phone number.", 409)
        g.set_phone(phone)
    if "relationship" in d:
        g.relationship = services._clean_name(d["relationship"])[:30]
    if "has_whatsapp" in d:
        g.has_whatsapp = bool(d["has_whatsapp"])
    if d.get("language") in ("sw", "en"):
        g.language = d["language"]
    g.save()
    audit(request.user, "guardian.edit", pk)
    return Response(_row(g, g.jobs.order_by("-id").first()))


@api_view(["GET"])
@permission_classes([IsAdminRole])
def guardian_reveal(request, pk):
    """Show one parent's full phone number. Every look is written to the audit log."""
    g = Guardian.objects.filter(pk=pk).first()
    if not g:
        return _err("Not found.", 404)
    audit(request.user, "guardian.reveal", pk)
    return Response({"name": g.name, "phone": g.phone})


@api_view(["POST", "DELETE"])
@permission_classes([IsAdminRole])
def guardian_links(request, pk):
    g = Guardian.objects.filter(pk=pk).first()
    if not g:
        return _err("Not found.", 404)
    if request.method == "POST":
        key = str(request.data.get("student_index") or "").strip().lower()
        s = services.student_lookup().get(key)
        if not s:
            return _err("No active student has that index number.", 404)
        GuardianLink.objects.get_or_create(guardian=g, student=s)
        audit(request.user, "guardian.link", pk, student=s.pk)
    else:
        GuardianLink.objects.filter(guardian=g, student_id=request.query_params.get("student")).delete()
        audit(request.user, "guardian.unlink", pk)
    return Response(_row(g, g.jobs.order_by("-id").first()))


@api_view(["GET"])
@permission_classes([IsAdminRole])
def template(request):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="parents_template.csv"'
    w = csv.writer(resp)
    w.writerow(services.TEMPLATE_COLUMNS)
    w.writerow(["Mama Amina", "0712345678", "mother", "S0100", "yes", "sw"])
    w.writerow(["Baba Neema", "0755123456", "father", "S0101;S0107", "no", "sw"])
    return resp


@api_view(["POST"])
@permission_classes([IsAdminRole])
def upload(request):
    """Send the file with confirm=false to check it (nothing is saved), then again with confirm=true to save."""
    f = request.FILES.get("file")
    if not f:
        return _err("Please choose a file.")
    try:
        rows = services.parse_file(f)
    except ValueError as e:
        return _err(str(e))
    except Exception:
        return _err("We could not read that file. Please use the template.")
    clean, report = services.validate_rows(rows)
    if str(request.data.get("confirm")).lower() not in ("true", "1"):
        return Response(report)
    if report["invalid_rows"] and str(request.data.get("skip_invalid")).lower() not in ("true", "1"):
        return _err("Some rows have problems. Fix the file, or confirm with 'skip invalid rows'.")
    out = services.commit_rows(clean, request.user)
    audit(request.user, "guardian.upload", len(clean), **out)
    return Response({**out, "skipped": report["invalid_rows"]})


@api_view(["GET"])
@permission_classes([IsAdminRole])
def summary(request):
    students = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False)
    linked = set(GuardianLink.objects.values_list("student_id", flat=True))
    without = [s for s in students.select_related("school_class") if s.pk not in linked]
    counts = {s: SmsJob.objects.filter(status=s).count() for s in (SmsJob.QUEUED, SmsJob.SENDING, SmsJob.SENT, SmsJob.DELIVERED, SmsJob.FAILED)}
    cutoff = timezone.now() - timedelta(seconds=ONLINE_SECONDS)
    return Response({
        "parents": Guardian.objects.count(), "students": students.count(), "students_with_parent": students.count() - len(without),
        "students_waiting_first_login": students.filter(must_change_password=True).count(),
        "without_parent": [{"id": s.pk, "name": f"{s.first_name} {s.last_name}".strip(), "index": s.index_number,
                            "class": str(s.school_class) if s.school_class_id else ""} for s in without[:40]],
        "default_messages": services.DEFAULT_MESSAGES, "jobs": counts, "phone_online": SmsDevice.objects.filter(active=True, last_seen__gte=cutoff).exists(),
    })


@api_view(["POST"])
@permission_classes([IsAdminRole])
def send(request):
    """Queue login messages. scope: all | class | selected.  dry_run=true only counts, changes nothing."""
    d = request.data
    scope = d.get("scope", "all")
    if scope not in ("all", "class", "selected"):
        return _err("Choose who to send to.")
    if scope == "class" and not d.get("class_id"):
        return _err("Choose a class.")
    resend = d.get("resend") is True
    login = d.get("include_login") is not False  # unticked in the app = a custom message only
    note = services.clean_note(d.get("note"))
    limit = services.NOTE_MAX if login else services.CUSTOM_MAX
    if len(note) > limit:
        return _err(f"The message is too long ({len(note)} characters). Keep it to {limit} characters or fewer.")
    cfg = SmsConfig.load()
    if login:
        try:
            templates = services.check_templates(d)
        except ValueError as e:
            return _err(str(e))
        items, skipped = services.plan_send(scope, d.get("class_id"), d.get("guardian_ids"), resend)
    else:
        if not note:
            return _err("Write the message to send. With 'include login details' unticked, only your own text is sent.")
        templates = {}
        items, skipped = services.plan_custom(scope, d.get("class_id"), d.get("guardian_ids"))
    info = {"messages": len(items), "students": sum(len(k) for _, k in items), "skipped": skipped, "login": login,
            "whatsapp_parents": sum(1 for g, _ in items if g.has_whatsapp), "note": note,
            "preview": services.preview(items, cfg, note, templates, login)}
    if d.get("dry_run") is not False:
        return Response({"dry_run": True, **info})
    if login and not cfg.public_url.strip():
        return _err("First write the school's web address in the Phone tab. It goes into every message.")
    n = services.queue_send(items, request.user, note, templates) if login else services.queue_custom(items, request.user, note)
    audit(request.user, "sms.queue", n, scope=scope, resend=resend, students=info["students"], custom_note=bool(note),
          login=login, edited_wording=any(templates.values()))
    return Response({"dry_run": False, "queued": n, **info}, status=201)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def jobs(request):
    p = request.query_params
    qs = SmsJob.objects.select_related("guardian", "device").order_by("-id")
    if p.get("status"):
        qs = qs.filter(status=p["status"])
    def row(j):
        return {"id": j.pk, "parent": j.guardian.name if j.guardian else "(deleted)", "phone": mask(crypto.decrypt(j.to_enc)),
                "summary": j.summary, "note": j.note, "login": j.login, "status": j.status, "error": j.error, "attempts": j.attempts,
                "whatsapp": bool(j.guardian and j.guardian.has_whatsapp), "created_at": j.created_at, "sent_at": j.sent_at,
                "phone_name": j.device.name if j.device else ""}
    paged = paginate(request, qs, default=20, row=row)
    return Response(paged if paged is not None else [row(j) for j in qs[:200]])


@api_view(["POST"])
@permission_classes([IsAdminRole])
def job_retry(request, pk=None):
    """Retry one failed message (pk) or every failed message (no pk)."""
    qs = SmsJob.objects.filter(status__in=(SmsJob.FAILED, SmsJob.CANCELLED), pk=pk) if pk else SmsJob.objects.filter(status=SmsJob.FAILED)
    n = sum(1 for j in qs if services.requeue(j, request.user))
    audit(request.user, "sms.retry", pk or "all", count=n)
    return Response({"requeued": n})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def job_cancel_queued(request):
    """Stop everything still waiting. Students in those messages keep a password nobody knows: send again (with 'reset')."""
    qs = SmsJob.objects.filter(status=SmsJob.QUEUED)
    n = qs.update(status=SmsJob.CANCELLED, body_enc="", error="Cancelled by an admin.")
    audit(request.user, "sms.cancel", "queued", count=n)
    return Response({"cancelled": n})


# ---------------------------------------------------------------- phones and settings
def _device_row(d):
    online = bool(d.last_seen and d.last_seen >= timezone.now() - timedelta(seconds=ONLINE_SECONDS))
    return {"id": d.pk, "name": d.name, "active": d.active, "online": online, "last_seen": d.last_seen, "created_at": d.created_at,
            "sent": d.jobs.filter(status__in=SmsJob.DONE).count()}


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def devices(request):
    if request.method == "POST":
        name = services._clean_name(request.data.get("name")) or "School phone"
        token = secrets.token_urlsafe(32)
        d = SmsDevice.objects.create(name=name, token_hash=hashlib.sha256(token.encode()).hexdigest(), created_by=request.user)
        audit(request.user, "sms.device.create", d.pk)
        return Response({**_device_row(d), "token": token}, status=201)  # the only time the token is shown
    qs = SmsDevice.objects.order_by("-id")
    return Response(paginate(request, qs, default=10, row=_device_row) or [_device_row(d) for d in qs])


@api_view(["DELETE"])
@permission_classes([IsAdminRole])
def device_detail(request, pk):
    d = SmsDevice.objects.filter(pk=pk).first()
    if not d:
        return _err("Not found.", 404)
    SmsJob.objects.filter(device=d, status=SmsJob.SENDING).update(status=SmsJob.QUEUED, device=None, leased_until=None)
    d.delete()
    audit(request.user, "sms.device.revoke", pk)
    return Response(status=204)


@api_view(["GET", "PATCH"])
@permission_classes([IsAdminRole])
def config(request):
    c = SmsConfig.load()
    if request.method == "PATCH":
        d = request.data
        if "public_url" in d:
            c.public_url = str(d["public_url"]).strip().replace("https://", "").replace("http://", "").rstrip("/")[:120]
        for f, lo, hi in (("seconds_between", 3, 120), ("pause_every", 5, 100), ("pause_seconds", 30, 1800)):
            if f in d:
                try:
                    v = int(d[f])
                except (TypeError, ValueError):
                    return _err(f"{f} must be a number.")
                if not lo <= v <= hi:
                    return _err(f"{f} must be between {lo} and {hi}.")
                setattr(c, f, v)
        c.save()
        audit(request.user, "sms.config", 1)
    return Response({"public_url": c.public_url, "seconds_between": c.seconds_between, "pause_every": c.pause_every, "pause_seconds": c.pause_seconds})


# ---------------------------------------------------------------- the phone app talks to these two
def _device(request):
    token = request.headers.get("X-Device-Token", "")
    if not token:
        return None
    d = SmsDevice.objects.filter(token_hash=hashlib.sha256(token.encode()).hexdigest(), active=True).first()
    if d:
        d.last_seen = timezone.now()
        d.save(update_fields=["last_seen"])
    return d


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def sms_pull(request):
    d = _device(request)
    if not d:
        return _err("Unknown phone. Pair it again from the Phone tab.", 401)
    try:
        limit = max(1, min(20, int(request.query_params.get("limit", 10))))
    except ValueError:
        limit = 10
    c = SmsConfig.load()
    return Response({"jobs": services.lease_jobs(d, limit),
                     "config": {"seconds_between": c.seconds_between, "pause_every": c.pause_every, "pause_seconds": c.pause_seconds}})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def sms_ping(request):
    """Lets the phone app check its pairing code without taking any messages."""
    d = _device(request)
    if not d:
        return _err("Unknown phone. Pair it again from the Phone tab.", 401)
    return Response({"ok": True, "name": d.name, "waiting": SmsJob.objects.filter(status=SmsJob.QUEUED).count()})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def sms_report(request):
    d = _device(request)
    if not d:
        return _err("Unknown phone.", 401)
    ok = services.apply_report(d, request.data.get("id"), request.data.get("status"), str(request.data.get("error") or ""))
    return Response({"ok": ok})
