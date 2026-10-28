from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from core.models import audit
from . import services
from .models import Announcement, Notification, PushSubscription


def _row(n):
    return {"id": n.pk, "kind": n.kind, "title": n.title, "body": n.body, "data": n.data,
            "created_at": n.created_at, "read": n.read_at is not None}


@api_view(["GET"])
def notification_list(request):
    """Own notifications only (BR-07). Students also get any reminder that is due right now."""
    if request.user.is_student:
        services.ensure_for_student(request.user)
    qs = Notification.objects.filter(user=request.user)
    unread = qs.filter(read_at__isnull=True).count()
    if request.query_params.get("unread") == "1":
        qs = qs.filter(read_at__isnull=True)
    return Response({"unread": unread, "items": [_row(n) for n in qs[:50]]})


@api_view(["POST"])
def notifications_read(request):
    qs = Notification.objects.filter(user=request.user, read_at__isnull=True)
    if not request.data.get("all"):
        ids = request.data.get("ids") or []
        if not isinstance(ids, list):
            raise ValidationError({"ids": "Send a list of notification ids."})
        qs = qs.filter(pk__in=[i for i in ids if isinstance(i, int)])
    return Response({"marked": qs.update(read_at=timezone.now())})


@api_view(["GET"])
def push_public_key(request):
    return Response({"public_key": settings.VAPID_PUBLIC_KEY or None})


@api_view(["POST"])
def push_subscribe(request):
    d = request.data
    keys = d.get("keys") or {}
    if not (d.get("endpoint") and keys.get("p256dh") and keys.get("auth")):
        raise ValidationError({"detail": "Missing subscription details."})
    PushSubscription.objects.update_or_create(
        endpoint=str(d["endpoint"])[:500],
        defaults={"user": request.user, "p256dh": keys["p256dh"], "auth": keys["auth"]},
    )
    return Response({"ok": True}, status=201)


@api_view(["POST"])
def push_unsubscribe(request):
    PushSubscription.objects.filter(user=request.user, endpoint=request.data.get("endpoint", "")).delete()
    return Response({"ok": True})


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def announcements(request):
    """NOT-03."""
    if request.method == "GET":
        return Response([{"id": a.pk, "title": a.title, "audience": a.audience, "target": a.target,
                          "recipients": a.recipients, "created_at": a.created_at}
                         for a in Announcement.objects.all()[:100]])
    title, body = (request.data.get("title") or "").strip(), (request.data.get("body") or "").strip()
    audience = request.data.get("audience", "all")
    if not title or not body:
        raise ValidationError({"detail": "Please write a title and a message."})
    if audience not in ("all", "class", "stream"):
        raise ValidationError({"audience": "Choose all, class or stream."})
    target = {}
    if audience == "class":
        ids = request.data.get("class_ids") or []
        if not ids or not isinstance(ids, list):
            raise ValidationError({"class_ids": "Choose at least one class."})
        target = {"class_ids": [int(i) for i in ids]}
    if audience == "stream":
        if not str(request.data.get("stream", "")).strip():
            raise ValidationError({"stream": "Enter the stream."})
        target = {"stream": str(request.data["stream"]).strip()}
        if request.data.get("form_level"):
            target["form_level"] = int(request.data["form_level"])
    students = list(services.audience_students(audience, target).values_list("pk", flat=True))
    ann = Announcement.objects.create(created_by=request.user, title=title[:160], body=body, audience=audience,
                                      target=target, recipients=len(students))
    services.notify(students, "announcement", title[:160], body, data={"announcement_id": ann.pk})
    audit(request.user, "announcement.send", ann.pk, audience=audience, recipients=len(students))
    return Response({"id": ann.pk, "recipients": len(students)}, status=201)
