from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from core.models import audit
from core.pagination import paginate
from . import services
from accounts.models import User
from .models import AdminMessage, Announcement, Notification, PushSubscription


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
    paged = paginate(request, qs, row=_row)
    if paged is not None:
        return Response({"unread": unread, "items": paged["results"], **{k: v for k, v in paged.items() if k != "results"}})
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


# ------------------------------------------------------------------ admin messages to one account

MESSAGE_MAX = 1000
MESSAGE_RECIPIENTS_MAX = 30


def _message(m):
    return {"id": m.pk, "body": m.body, "created_at": m.created_at, "dismissed": m.dismissed_at is not None}


@api_view(["GET"])
def my_messages(request):
    """Own messages only. ?banner=1 returns just the ones still to be shown as a banner (newest first)."""
    qs = AdminMessage.objects.filter(recipient=request.user)
    unseen = qs.filter(dismissed_at__isnull=True)
    count = unseen.count()
    if request.query_params.get("banner") == "1":
        return Response({"unseen": count, "items": [_message(m) for m in unseen[:5]]})
    return Response({"unseen": count, "items": [_message(m) for m in qs[:200]]})


@api_view(["POST"])
def dismiss_message(request, message_id):
    """The person closed the banner. The message stays in her Messages tab."""
    m = get_object_or_404(AdminMessage, pk=message_id, recipient=request.user)
    if not m.dismissed_at:
        m.dismissed_at = timezone.now()
        m.save(update_fields=["dismissed_at"])
    return Response({"ok": True})


def _sent(m):
    r = m.recipient
    return {"id": m.pk, "body": m.body, "created_at": m.created_at, "seen": m.dismissed_at is not None, "seen_at": m.dismissed_at,
            "recipient": {"id": r.pk, "name": (f"{r.first_name} {r.last_name}".strip() or r.username), "role": r.role, "index": r.index_number}}


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def admin_messages(request):
    """GET: messages sent (?user=<id> for one account). POST {recipients: [ids], body}: send the same message to each account."""
    if request.method == "GET":
        qs = AdminMessage.objects.select_related("recipient")
        if request.query_params.get("user"):
            qs = qs.filter(recipient_id=request.query_params["user"])
        return Response({"results": [_sent(m) for m in qs[:300]]})
    body = str(request.data.get("body") or "").strip()
    ids = request.data.get("recipients")
    if not body:
        raise ValidationError({"body": "Write the message first."})
    if len(body) > MESSAGE_MAX:
        raise ValidationError({"body": f"Please keep the message under {MESSAGE_MAX} characters."})
    if not isinstance(ids, list) or not 1 <= len(set(map(str, ids))) <= MESSAGE_RECIPIENTS_MAX:
        raise ValidationError({"recipients": f"Choose from 1 to {MESSAGE_RECIPIENTS_MAX} people."})
    try:
        ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        raise ValidationError({"recipients": "Choose people from the list."})
    people = list(User.objects.filter(pk__in=ids, role__in=[User.Role.STUDENT, User.Role.TEACHER], is_archived=False))
    if len(people) != len(ids):
        raise ValidationError({"recipients": "Messages can be sent to current students and teachers."})
    made = [AdminMessage.objects.create(recipient=u, sender=request.user, body=body) for u in people]
    audit(request.user, "message.send", f"{len(made)} message(s)", recipients=ids)
    return Response({"ok": True, "sent": len(made)}, status=201)


@api_view(["DELETE"])
@permission_classes([IsAdminRole])
def admin_message_delete(request, message_id):
    """Deleting removes the message from the person's Messages tab (and her banner) for good."""
    m = get_object_or_404(AdminMessage, pk=message_id)
    audit(request.user, "message.delete", f"message {m.pk}", recipient=m.recipient_id)
    m.delete()
    return Response({"ok": True})
