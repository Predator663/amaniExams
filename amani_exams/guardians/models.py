from django.conf import settings
from django.db import models

from . import crypto


class Guardian(models.Model):
    """A parent or guardian. Name and phone number are stored encrypted (see crypto.py)."""

    name_enc = models.TextField()
    phone_enc = models.TextField()
    phone_idx = models.CharField(max_length=64, unique=True)  # keyed hash of the phone, for finding duplicates
    relationship = models.CharField(max_length=30, blank=True)
    has_whatsapp = models.BooleanField(default=False)
    language = models.CharField(max_length=2, default="sw")  # language of the SMS
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        return crypto.decrypt(self.name_enc)

    @property
    def phone(self):
        return crypto.decrypt(self.phone_enc)

    def set_name(self, v):
        self.name_enc = crypto.encrypt(v)

    def set_phone(self, v):
        self.phone_enc = crypto.encrypt(v)
        self.phone_idx = crypto.blind_index(v)


class GuardianLink(models.Model):
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="links")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="guardian_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("guardian", "student")


class SmsConfig(models.Model):
    """Singleton row (pk=1): how the phone paces its messages and what web address the SMS shows."""

    public_url = models.CharField(max_length=120, default="")
    seconds_between = models.PositiveIntegerField(default=8)
    pause_every = models.PositiveIntegerField(default=30)
    pause_seconds = models.PositiveIntegerField(default=180)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SmsDevice(models.Model):
    """An Android phone that sends the SMS. Only a hash of its secret token is stored."""

    name = models.CharField(max_length=60)
    token_hash = models.CharField(max_length=64, unique=True)
    active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class SmsJob(models.Model):
    QUEUED, SENDING, SENT, DELIVERED, FAILED, CANCELLED = "queued", "sending", "sent", "delivered", "failed", "cancelled"
    STATUSES = [(s, s) for s in (QUEUED, SENDING, SENT, DELIVERED, FAILED, CANCELLED)]
    OPEN = (QUEUED, SENDING)
    DONE = (SENT, DELIVERED)

    guardian = models.ForeignKey(Guardian, null=True, on_delete=models.SET_NULL, related_name="jobs")
    students = models.JSONField(default=list)  # ids of the students whose details are in the message
    summary = models.CharField(max_length=200, blank=True)  # e.g. "Login details for Amina Juma" (never the password)
    to_enc = models.TextField()
    body_enc = models.TextField(blank=True)  # holds passwords, so it is erased as soon as the SMS has been sent
    status = models.CharField(max_length=10, choices=STATUSES, default=QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=200, blank=True)
    device = models.ForeignKey(SmsDevice, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    leased_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
