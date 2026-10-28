from django.conf import settings
from django.db import models


class LegalAcceptance(models.Model):
    """A student ticked the Terms of use and Privacy policy (which cover location monitoring) before starting an exam."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="legal_acceptances")
    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="+")
    version = models.CharField(max_length=20)  # the policy version she saw, see settings.LEGAL_VERSION
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "exam"], name="pr_accept_user_exam")]


class LiveLocation(models.Model):
    """The latest known position of a student during one attempt. One row per attempt, overwritten on every report,
    so the system never builds a movement history. Rows of finished attempts are removed by `purge_locations`."""

    attempt = models.OneToOneField("exams.Attempt", on_delete=models.CASCADE, related_name="live_location")
    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="+")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    lat = models.FloatField()
    lng = models.FloatField()
    accuracy = models.FloatField(default=0)  # metres, as reported by the phone (GNSS + Wi-Fi + mobile network fused by the OS)
    speed = models.FloatField(null=True, blank=True)  # m/s
    heading = models.FloatField(null=True, blank=True)  # degrees
    anchor_lat = models.FloatField(null=True, blank=True)  # where she was last judged to be standing still
    anchor_lng = models.FloatField(null=True, blank=True)
    moving_until = models.DateTimeField(null=True, blank=True)
    moving_source = models.CharField(max_length=10, blank=True)  # gps | motion
    sensors = models.JSONField(default=dict, blank=True)  # permission / bluetooth / network / motion status reported by the phone
    updated_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["exam", "updated_at"], name="pr_loc_exam_upd"), models.Index(fields=["lat", "lng"], name="pr_loc_latlng")]


class ProximityAlert(models.Model):
    """Two students of the same exam were closer than the alert distance. Information for administrators, never proof of cheating."""

    CONFIRMED, POSSIBLE = "confirmed", "possible"

    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="proximity_alerts")
    a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")  # a.pk < b.pk
    b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    min_distance = models.FloatField()
    last_distance = models.FloatField()
    confidence = models.CharField(max_length=10, default=POSSIBLE)
    active = models.BooleanField(default=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)  # both positions at the closest moment (evidence for the review)

    class Meta:
        ordering = ["-last_seen"]
        indexes = [models.Index(fields=["exam", "active"], name="pr_alert_exam_active")]
