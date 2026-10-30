"""Two middlewares.

MaintenanceMiddleware  - place it right AFTER corsheaders' CorsMiddleware (so the 503 carries CORS headers and the web app can read it).
                         While maintenance is on, every request is answered 503 (JSON for /api/, a small page otherwise) unless it is
                         - to an exempt path (/django-admin/, /controlroom/, /static/, /api/site-status/ ...),
                         - made with the OWNER's login token (Authorization: Token ...), or
                         - the owner signing in (POST /api/auth/login/ with the owner's user name).
OwnerOnlyMiddleware    - place it AFTER AuthenticationMiddleware. During maintenance only the owner may use /django-admin/ and /controlroom/.
"""
import json

from django.http import HttpResponse, JsonResponse
from django.utils.html import escape

from . import state

LOGIN_PATH = "/api/auth/login/"


def bearer_user(request):
    """The user behind 'Authorization: Token <key>' (the web app's login), or None."""
    h = request.META.get("HTTP_AUTHORIZATION", "")
    if h[:6].lower() != "token ":
        return None
    from rest_framework.authtoken.models import Token
    t = Token.objects.select_related("user").filter(key=h[6:].strip()).first()
    return t.user if t else None


def has_pass(request):
    return state.is_owner(bearer_user(request))


def owner_is_signing_in(request):
    """Lets ONLY the owner's own username through the login endpoint, so the owner can use the web app while it is off for everyone else."""
    if request.method != "POST" or request.path != LOGIN_PATH:
        return False
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > 4096:
            return False
        name = str(json.loads(request.body or b"{}").get("username") or "").strip()
    except (ValueError, TypeError, AttributeError):
        return False
    if not name:
        return False
    from django.contrib.auth import get_user_model
    u = get_user_model().objects.filter(username__iexact=name).first()
    return state.is_owner(u)


PAGE = """<!doctype html><html lang="sw"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Maintenance / Matengenezo</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;padding:20px}}
.c{{max-width:520px;text-align:center}}h1{{font-size:26px;margin:.2em 0}}p{{line-height:1.5;color:#cbd5e1}}
.b{{display:inline-block;margin-top:12px;padding:6px 12px;border-radius:99px;background:#1e293b;color:#fbbf24;font-size:14px}}
hr{{border:0;border-top:1px solid #334155;margin:22px 0}}</style></head><body><div class="c">
<div style="font-size:54px">🛠️</div>
<h1>Mfumo uko kwenye matengenezo</h1>
<p>Tunafanya maboresho kwa muda mfupi. Tafadhali jaribu tena baadaye.</p>
{sw_extra}
<hr>
<h1>Down for maintenance</h1>
<p>We are making improvements and will be back shortly. Please try again later.</p>
{en_extra}
</div></body></html>"""


def maintenance_response(request, message="", back_at=""):
    if request.path.startswith("/api/"):
        r = JsonResponse({"detail": "The system is under maintenance. Please try again later.", "code": "maintenance",
                          "message": message, "back_at": back_at}, status=503)
    else:
        sw = (f'<p><b>{escape(message)}</b></p>' if message else "") + (f'<span class="b">Tutarudi: {escape(back_at)}</span>' if back_at else "")
        en = (f'<p><b>{escape(message)}</b></p>' if message else "") + (f'<span class="b">Back: {escape(back_at)}</span>' if back_at else "")
        r = HttpResponse(PAGE.format(sw_extra=sw, en_extra=en), status=503, content_type="text/html; charset=utf-8")
    r["Retry-After"] = "600"
    r["Cache-Control"] = "no-store"
    return r


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        on, message, back_at = state.current()
        if on and not request.path.startswith(state.exempt_prefixes()) and not has_pass(request) and not owner_is_signing_in(request):
            return maintenance_response(request, message, back_at)
        return self.get_response(request)


class OwnerOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (state.current()[0] and request.path.startswith(("/django-admin/", "/controlroom/"))
                and request.user.is_authenticated and not state.is_owner(request.user)):
            return maintenance_response(request, "Owner access only.")
        return self.get_response(request)
