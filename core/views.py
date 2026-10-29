import io

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, authentication_classes, parser_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.models import THEMES
from accounts.permissions import IsAdminRole
from . import i18n
from . import grading
from .pagination import page_params, wants_page
from .models import AuditLog, SchoolSettings, audit

ONLINE_WINDOW_SECONDS = 90
_IDS_KEY, _COUNT_KEY = "online:student_ids", "online:count"


def _heartbeat_key(uid):
    return f"online:{uid}"


def _student_ids():
    """Ids of students who can be online. Cached for two minutes so a heartbeat does not hit the database."""
    ids = cache.get(_IDS_KEY)
    if ids is None:
        from accounts.models import User
        ids = list(User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False).values_list("pk", flat=True))
        cache.set(_IDS_KEY, ids, 120)
    return ids


def online_ids(extra=()):
    """User ids with a heartbeat in the last 90 seconds (used by the admin live monitor).
    One cache key per student, so 500 heartbeats in the same second never overwrite each other."""
    ids = set(_student_ids()) | set(extra)
    seen = cache.get_many([_heartbeat_key(i) for i in ids])
    now_ts = timezone.now().timestamp()
    return {int(k.split(":")[1]) for k, ts in seen.items() if now_ts - ts <= ONLINE_WINDOW_SECONDS}


@api_view(["POST", "GET"])
def presence(request):
    """POST = heartbeat from a logged-in student (call every ~30s). GET/POST both return the
    number only (BR-08). Needs a cache shared by all server processes (Redis, see REDIS_URL)."""
    if request.method == "POST":
        cache.set(_heartbeat_key(request.user.pk), timezone.now().timestamp(), ONLINE_WINDOW_SECONDS + 30)
    count = cache.get(_COUNT_KEY)
    if count is None or request.method == "POST" and request.user.pk not in _student_ids():
        count = len(online_ids(extra=[request.user.pk]))
        cache.set(_COUNT_KEY, count, 5)  # at most one count every 5 seconds, however many students ask
    return Response({"online": count})


SETTINGS_FIELDS = [
    "school_name", "result_delay_minutes", "late_entry_minutes", "question_approval_required",
    "show_class_position", "leaderboard_enabled", "grade_scale", "rules_text", "default_theme", "default_language",
    "proximity_alert_meters", "proximity_lock_enabled",
]


def _settings_payload(s):
    d = {f: getattr(s, f) for f in SETTINGS_FIELDS}
    d["logo_url"] = s.logo.url if s.logo else None
    return d


def clean_settings(data):
    """Validate an admin PATCH. Returns (clean_values, errors)."""
    clean, errors = {}, {}
    for name, lo, hi in (("result_delay_minutes", 0, 1440), ("late_entry_minutes", 0, 180)):
        if name in data:
            try:
                v = int(data[name])
            except (TypeError, ValueError):
                errors[name] = "Enter a whole number."
                continue
            if not lo <= v <= hi:
                errors[name] = f"Enter a number from {lo} to {hi}."
            else:
                clean[name] = v
    if "proximity_alert_meters" in data:
        try:
            v = float(data["proximity_alert_meters"])
            if v != v:
                raise ValueError
        except (TypeError, ValueError):
            errors["proximity_alert_meters"] = "Enter a distance in metres."
        else:
            if not 1 <= v <= 500:
                errors["proximity_alert_meters"] = "Enter a distance from 1 to 500 metres."
            else:
                clean["proximity_alert_meters"] = round(v, 1)
    for name in ("question_approval_required", "show_class_position", "leaderboard_enabled", "proximity_lock_enabled"):
        if name in data:
            if isinstance(data[name], bool):
                clean[name] = data[name]
            else:
                errors[name] = "Must be true or false."
    if "school_name" in data:
        v = str(data["school_name"]).strip()
        if not v or len(v) > 200:
            errors["school_name"] = "Enter the school name (up to 200 characters)."
        else:
            clean["school_name"] = v
    if "rules_text" in data:
        clean["rules_text"] = str(data["rules_text"])[:5000]
    if "default_theme" in data:
        if data["default_theme"] in THEMES:
            clean["default_theme"] = data["default_theme"]
        else:
            errors["default_theme"] = "Unknown theme."
    if "default_language" in data:
        if data["default_language"] in ("en", "sw"):
            clean["default_language"] = data["default_language"]
        else:
            errors["default_language"] = "Choose en or sw."
    if "grade_scale" in data:
        problems = grading.validate_scale(data["grade_scale"])
        if problems:
            errors["grade_scale"] = problems
        else:
            clean["grade_scale"] = grading.normalize_scale(data["grade_scale"])  # GRD-04 / RES-07
    return clean, errors


@api_view(["GET", "PATCH"])
def school_settings(request):
    s = SchoolSettings.load()
    if request.method == "PATCH":
        if not IsAdminRole().has_permission(request, None):
            return Response({"detail": "Not allowed."}, status=403)
        clean, errors = clean_settings(request.data)
        if errors:
            return Response({"detail": "Some settings are not valid.", "errors": errors}, status=400)
        for f, v in clean.items():
            setattr(s, f, v)
        s.save()
        audit(request.user, "settings.update", 1, fields=sorted(clean))
    return Response(_settings_payload(s))


@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([IsAdminRole])
def settings_logo(request):
    """ADM-09: school logo. Resized and stored as PNG."""
    from PIL import Image, UnidentifiedImageError

    f = request.FILES.get("logo")
    if not f:
        return Response({"detail": "Please choose an image."}, status=400)
    if f.size > 5 * 1024 * 1024:
        return Response({"detail": "Image is too large (max 5 MB)."}, status=400)
    try:
        img = Image.open(f)
        img.load()
    except (UnidentifiedImageError, OSError):
        return Response({"detail": "That file is not a valid image."}, status=400)
    img.thumbnail((512, 512))
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    s = SchoolSettings.load()
    s.logo.save("logo.png", ContentFile(buf.getvalue()), save=True)
    audit(request.user, "settings.logo", 1)
    return Response({"logo_url": s.logo.url})


@api_view(["GET"])
def audit_log(request):
    """ADM-10. Filters: actor (username), action (prefix), from / to (YYYY-MM-DD); paging: limit, offset."""
    if not IsAdminRole().has_permission(request, None):
        return Response({"detail": "Not allowed."}, status=403)
    p = request.query_params
    qs = AuditLog.objects.select_related("actor")
    if p.get("actor"):
        qs = qs.filter(actor__username__iexact=p["actor"])
    if p.get("action"):
        qs = qs.filter(action__startswith=p["action"])
    for key, lookup in (("from", "created_at__date__gte"), ("to", "created_at__date__lte")):
        try:
            d = parse_date(p.get(key, ""))
        except ValueError:
            d = None
        if d:
            qs = qs.filter(**{lookup: d})
    total = qs.count()
    page = pages = None
    if wants_page(request):
        page, limit = page_params(request, 25)
        pages = max(1, -(-total // limit))
        page = min(page, pages)
        offset = (page - 1) * limit
    else:
        try:
            limit = max(1, min(int(p.get("limit", 100)), 500))
            offset = max(0, int(p.get("offset", 0)))
        except ValueError:
            limit, offset = 100, 0
    return Response({
        "count": total,
        **({"page": page, "pages": pages, "page_size": limit} if page else {}),
        "results": [
            {"at": r.created_at, "actor": getattr(r.actor, "username", None), "action": r.action,
             "target": r.target, "detail": r.detail}
            for r in qs[offset:offset + limit]
        ],
    })


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def i18n_catalog(request, lang):
    """ACC-08: server-side English or Swahili text, badge and level names, for the app to use. Public, no secrets."""
    return Response(i18n.catalog_for(lang))
