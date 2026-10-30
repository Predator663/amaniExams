"""God's Eye: read-only look at everything. Works on whatever models the project has; nothing here knows the Amani field names."""
import re
from datetime import timedelta

from django.apps import apps
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import models as dj
from django.utils import timezone

HIDE = re.compile(r"(password|passwd|secret|token|api_?key|^key$|private|_enc$|^enc_|_idx$|hash|otp|salt|signature|credential|(^|_)auth($|_)|p256dh|session_(key|data))", re.I)
HIDDEN = "••• hidden"


def all_models():
    return sorted((m for m in apps.get_models() if not m._meta.proxy), key=lambda m: m._meta.label_lower)


def admin_url(m):
    """Address of the model's list in /django-admin/, or "" when it has no admin."""
    from django.contrib import admin
    from django.urls import NoReverseMatch, reverse
    if not admin.site.is_registered(m):
        return ""
    try:
        return reverse(f"admin:{m._meta.app_label}_{m._meta.model_name}_changelist")
    except NoReverseMatch:
        return ""


def get_model(label):
    try:
        return apps.get_model(label)
    except (LookupError, ValueError):
        return None


def value(obj, field):
    if HIDE.search(field.name) or isinstance(field, dj.BinaryField):
        return HIDDEN
    try:
        v = getattr(obj, field.name)
    except Exception:
        return "?"
    if v is None:
        return ""
    s = str(v)
    return s if len(s) <= 160 else s[:157] + "…"


def row(obj, limit=8):
    fields = [f for f in obj._meta.concrete_fields if not f.primary_key][:limit]
    secret_pk = bool(HIDE.search(obj._meta.pk.name))  # e.g. an auth token's key IS its primary key
    return {"id": HIDDEN if secret_pk else obj.pk, "label": HIDDEN if secret_pk else str(obj)[:120],
            "values": {f.name: value(obj, f) for f in fields}}


def counts():
    out = []
    for m in all_models():
        try:
            n = m._default_manager.count()
        except Exception:
            n = None
        out.append({"label": m._meta.label_lower, "name": str(m._meta.verbose_name_plural).title(), "count": n,
                    "admin_url": admin_url(m)})
    return out


def online_users():
    """Who is online right now: the web app's heartbeat (last ~90 s, the same source as the live monitor) plus anyone holding a Django-admin session."""
    User = get_user_model()
    ids = set()
    try:
        from core.views import online_ids
        ids |= {str(i) for i in online_ids()}
    except Exception:
        pass
    try:
        for s in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
            uid = s.get_decoded().get("_auth_user_id")
            if uid:
                ids.add(str(uid))
    except Exception:
        pass
    out = []
    for u in User.objects.filter(pk__in=ids).order_by("-last_login")[:300]:
        out.append({"id": u.pk, "user": u.get_username(), "name": (u.get_full_name() or "")[:60],
                    "role": str(getattr(u, "role", "") or ("superuser" if u.is_superuser else "staff" if u.is_staff else "")),
                    "last_login": u.last_login.isoformat() if u.last_login else ""})
    return out


def recent_logins(n=15):
    User = get_user_model()
    return [{"user": u.get_username(), "at": u.last_login.isoformat()}
            for u in User.objects.exclude(last_login=None).order_by("-last_login")[:n]]


def admin_log(n=15):
    return [{"at": e.action_time.isoformat(), "user": e.user.get_username(), "what": str(e)[:140]}
            for e in LogEntry.objects.select_related("user").order_by("-action_time")[:n]]


def audit_rows(n=15):
    """Any model whose name says audit/activity/log (the project's own audit trail), newest first."""
    for m in all_models():
        name = m._meta.model_name
        if m is LogEntry or m is Session:
            continue
        if any(k in name for k in ("audit", "activity")):
            try:
                return {"model": m._meta.label_lower, "rows": [row(o) for o in m._default_manager.order_by("-pk")[:n]]}
            except Exception:
                continue
    return None


def status_breakdown(label, field="status"):
    m = get_model(label)
    if not m or field not in [f.name for f in m._meta.fields]:
        return None
    return {r[field] or "": r["n"] for r in m._default_manager.values(field).annotate(n=dj.Count("pk"))}


def snapshot():
    User = get_user_model()
    now = timezone.now()
    return {
        "time": now.isoformat(),
        "users": {"total": User.objects.count(), "active": User.objects.filter(is_active=True).count(),
                  "superusers": User.objects.filter(is_superuser=True).count()},
        "online": online_users(),
        "recent_logins": recent_logins(),
        "admin_log": admin_log(),
        "audit": audit_rows(),
        "sms": status_breakdown("guardians.smsjob"),
        "counts": counts(),
    }


def text_fields(m):
    return [f.name for f in m._meta.concrete_fields if isinstance(f, (dj.CharField, dj.TextField))
            and not HIDE.search(f.name)]


def browse(m, q="", page=1, size=50):
    qs = m._default_manager.all().order_by("-pk")
    q = (q or "").strip()
    if q:
        cond = dj.Q()
        for f in text_fields(m):
            cond |= dj.Q(**{f + "__icontains": q})
        if q.isdigit() and m._meta.pk.get_internal_type().endswith("AutoField"):
            cond |= dj.Q(pk=int(q))
        qs = qs.filter(cond)
    total = qs.count()
    pages = max(1, -(-total // size))
    page = min(max(1, page), pages)
    objs = list(qs[(page - 1) * size: page * size])
    cols = [f.name for f in m._meta.concrete_fields]
    rows = [[value(o, m._meta.get_field(c)) for c in cols] for o in objs]
    return {"cols": cols, "rows": rows, "total": total, "page": page, "pages": pages}
