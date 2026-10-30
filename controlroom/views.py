import hmac
import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from rest_framework.authtoken.models import Token

from . import eye, state, words
from .middleware import has_pass
from .models import ControlEvent, SiteControl

PHRASE_TTL = 300  # seconds the typed phrase stays valid


def owner_only(view):
    @wraps(view)
    @never_cache
    def wrapper(request, *a, **kw):
        if not request.user.is_authenticated:
            return redirect(f"/django-admin/login/?next={request.path}")
        if not state.is_owner(request.user):
            return HttpResponseForbidden("Owner access only.")
        return view(request, *a, **kw)
    return wrapper


def _ip(request):
    return request.META.get("REMOTE_ADDR") or None


def _log(request, action, detail=""):
    ControlEvent.objects.create(who=request.user.get_username(), action=action, detail=detail[:500], ip=_ip(request))


def _new_phrase(request):
    request.session["cr_phrase"] = words.phrase()
    request.session["cr_phrase_at"] = timezone.now().timestamp()
    return request.session["cr_phrase"]


def _phrase(request):
    p, at = request.session.get("cr_phrase"), request.session.get("cr_phrase_at", 0)
    if not p or timezone.now().timestamp() - at > PHRASE_TTL:
        return _new_phrase(request)
    return p


@owner_only
def home(request):
    ctl = SiteControl.get()
    return render(request, "controlroom/home.html", {
        "ctl": ctl, "phrase": _phrase(request), "events": ControlEvent.objects.all()[:15],
        "title": "Control room", "owners": sorted(state.owners()) or ["any superuser"],
    })


@owner_only
@require_POST
def enable_maintenance(request):
    expected = request.session.get("cr_phrase", "")
    typed = " ".join((request.POST.get("phrase") or "").lower().split())
    fresh = timezone.now().timestamp() - request.session.get("cr_phrase_at", 0) <= PHRASE_TTL
    _new_phrase(request)  # one try per phrase: a wrong or used phrase is never reusable
    if not (expected and fresh and hmac.compare_digest(typed.encode(), expected.encode())):
        _log(request, "enable_refused", "wrong or expired confirmation phrase")
        messages.error(request, "The words did not match (or took too long). A new set of words is shown - the site is still ONLINE.")
        return redirect("controlroom:home")
    ctl = SiteControl.get()
    ctl.maintenance, ctl.started_at, ctl.started_by = True, timezone.now(), request.user.get_username()
    ctl.message = (request.POST.get("message") or "").strip()[:300]
    ctl.back_at = (request.POST.get("back_at") or "").strip()[:80]
    ctl.save()
    state.reset_cache()
    kicked = 0
    if request.POST.get("logout_all"):
        keep = request.session.session_key
        for s in Session.objects.exclude(session_key=keep):
            s.delete()
        kicked = Token.objects.exclude(user=request.user).delete()[0]  # the web app's logins: one token per signed-in person
    _log(request, "maintenance_on", f"message={ctl.message!r} back_at={ctl.back_at!r} tokens_cleared={kicked}")
    messages.warning(request, "Site is now in MAINTENANCE. Only you can get in." + (f" {kicked} logins signed out." if kicked else ""))
    return redirect("controlroom:home")


@owner_only
@require_POST
def disable_maintenance(request):
    ctl = SiteControl.get()
    ctl.maintenance = False
    ctl.save()
    state.reset_cache()
    _log(request, "maintenance_off")
    messages.success(request, "Site is back ONLINE for everyone.")
    return redirect("controlroom:home")


@owner_only
def god_eye(request):
    return render(request, "controlroom/eye.html", {"title": "God's Eye"})


@owner_only
def eye_data(request):
    return JsonResponse(eye.snapshot())


@owner_only
def models_index(request):
    return render(request, "controlroom/models.html", {"title": "Every table", "items": eye.counts()})


@owner_only
def model_rows(request, label):
    m = eye.get_model(label)
    if not m:
        raise Http404
    try:
        page = int(request.GET.get("page", 1))
    except ValueError:
        page = 1
    q = request.GET.get("q", "")
    data = eye.browse(m, q, page)
    return render(request, "controlroom/rows.html", {"title": str(m._meta.verbose_name_plural).title(), "label": label, "q": q, **data})


@never_cache
def site_status(request):
    """Public. The web app asks this to decide whether to show the maintenance screen. 'blocked' is False for the owner."""
    on, message, back_at = state.current()
    return JsonResponse({"maintenance": on, "blocked": bool(on and not has_pass(request)),
                         "message": message if on else "", "back_at": back_at if on else ""})
