from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    """In-app notification (NOT-01). `key` makes system notifications idempotent: the same
    key is never created twice for one user (for example 'exam1h:12')."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30)  # exam_reminder, exam_start, results_ready, password_changed, announcement
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    key = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], condition=~Q(key=""), name="uniq_notification_key"),
        ]


class Announcement(models.Model):
    """NOT-03: an admin message to all students, some classes, or a stream."""

    ALL, CLASS, STREAM = "all", "class", "stream"
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=160)
    body = models.TextField()
    audience = models.CharField(max_length=10, default=ALL)
    target = models.JSONField(default=dict, blank=True)
    recipients = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PushSubscription(models.Model):
    """NOT-02: a browser/phone that agreed to Web Push."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
