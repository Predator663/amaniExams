"""Maintenance state + owner rules. Kept tiny and defensive: if the table is missing (before migrate) the site is simply 'online'."""
import time

from django.conf import settings

_CACHE = {"at": 0.0, "val": None}
TTL = 3  # seconds; another worker notices a switch within this time


def owners():
    """Usernames allowed in during maintenance. CONTROLROOM_OWNERS='goose' (comma separated). Empty = any superuser."""
    v = getattr(settings, "CONTROLROOM_OWNERS", "") or ""
    if isinstance(v, str):
        v = v.split(",")
    return {x.strip().lower() for x in v if x.strip()}


def is_owner(user):
    if not (user and getattr(user, "is_authenticated", False) and user.is_active and user.is_superuser):
        return False
    allowed = owners()
    return not allowed or user.get_username().lower() in allowed


def exempt_prefixes():
    base = ["/django-admin/", "/controlroom/", "/static/", "/healthz", "/favicon.ico", "/api/site-status/"]
    return tuple(base + list(getattr(settings, "CONTROLROOM_EXEMPT_PREFIXES", [])))


def current(force=False):
    """(maintenance: bool, message: str, back_at: str)"""
    now = time.monotonic()
    if not force and _CACHE["val"] is not None and now - _CACHE["at"] < TTL:
        return _CACHE["val"]
    try:
        from .models import SiteControl
        row = SiteControl.objects.filter(pk=1).first()
        val = (bool(row and row.maintenance), row.message if row else "", row.back_at if row else "")
    except Exception:  # table missing / DB hiccup: never take the site down because of the switch itself
        val = (False, "", "")
    _CACHE.update(at=now, val=val)
    return val


def reset_cache():
    _CACHE.update(at=0.0, val=None)
