import copy

from django.conf import settings
from django.db import models

from .grading import DEFAULT_SCALE


def default_scale():
    return copy.deepcopy(DEFAULT_SCALE)


class SchoolSettings(models.Model):
    """Singleton row (pk=1) holding admin-editable settings (ADM-09)."""

    school_name = models.CharField(max_length=200, default="Amani Girls Secondary School")
    result_delay_minutes = models.PositiveIntegerField(default=5)  # BR-06
    late_entry_minutes = models.PositiveIntegerField(default=10)  # EXM-04
    question_approval_required = models.BooleanField(default=True)  # QB-09
    show_class_position = models.BooleanField(default=False)
    leaderboard_enabled = models.BooleanField(default=False)
    grade_scale = models.JSONField(default=default_scale)
    logo = models.ImageField(upload_to="school/", blank=True)  # ADM-09
    rules_text = models.TextField(blank=True, default="")  # default rules shown before an exam
    default_theme = models.CharField(max_length=20, default="light")
    default_language = models.CharField(max_length=2, default="en")
    proximity_alert_meters = models.FloatField(default=20)  # anti-cheat: two students closer than this raise an alert
    proximity_lock_enabled = models.BooleanField(default=False)  # anti-cheat: also lock both students' exam screens until an admin unlocks
    leave_lock_enabled = models.BooleanField(default=True)  # anti-cheat: lock a student's exam once she has left the exam screen more than leave_lock_limit times
    leave_lock_limit = models.PositiveSmallIntegerField(default=3)  # how many times she may leave; the next time locks her until an admin unlocks

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AuditLog(models.Model):
    """Append-only (ADM-10). Entries cannot be edited or deleted through the ORM."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=200, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit log entries cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries cannot be deleted.")


def audit(actor, action, target="", **detail):
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        target=str(target)[:200],
        detail=detail,
    )
