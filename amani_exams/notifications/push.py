"""Web Push (NOT-02). Entirely optional: with no VAPID keys or no `pywebpush` installed, every
function quietly does nothing and in-app notifications carry on working."""
import json
import logging
import threading

from django.conf import settings
from django.db import close_old_connections

log = logging.getLogger(__name__)


def configured():
    if not (settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY):
        return False
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return False
    return True


def send_push(user_ids, title, body="", url="/"):
    """Send in a background thread so a request never waits on hundreds of push services."""
    ids = list(user_ids)
    if ids and configured():
        threading.Thread(target=_worker, args=(ids, title, body, url), daemon=True).start()


def _worker(user_ids, title, body, url):
    from pywebpush import WebPushException, webpush

    from .models import PushSubscription

    try:
        payload = json.dumps({"title": title, "body": body, "url": url})
        for sub in PushSubscription.objects.filter(user_id__in=user_ids):
            try:
                webpush(
                    subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    data=payload, vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}"},
                )
            except WebPushException as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (404, 410):  # the phone unsubscribed
                    sub.delete()
                else:
                    log.warning("push failed: %s", e)
            except Exception:
                log.exception("push failed")
    finally:
        close_old_connections()
