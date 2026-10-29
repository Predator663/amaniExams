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
    devices = models.JSONField(default=dict, blank=True)  # {"first": {id, platform, ip}, "last": {...}}: which device reports for this attempt
    spoof = models.JSONField(default=dict, blank=True)    # consecutive-report counters for the fake-position checks (see spoof.py)
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
    # Exam lock (only when the admin switched "lock students who sit too close" on). Both students' screens stay locked
    # until an administrator unlocks the pair, even after they have moved apart. The exam clock is never paused.
    locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-last_seen"]
        indexes = [models.Index(fields=["exam", "active"], name="pr_alert_exam_active"),
                   models.Index(fields=["exam", "locked"], name="pr_alert_exam_locked")]


class IntegrityFlag(models.Model):
    """Something an administrator should look at: a device change or a sign of a faked position. Never proof, never automatic
    action. One row per attempt and kind; `count` says how many separate times it happened."""
    DEVICE_CHANGED, LOGIN_DURING_EXAM = "device_changed", "login_during_exam"
    TELEPORT, FROZEN, PERFECT, ROUNDED = "teleport", "frozen_fix", "perfect_accuracy", "rounded_coords"
    KINDS = [(DEVICE_CHANGED, "Device changed"), (LOGIN_DURING_EXAM, "Logged in again"), (TELEPORT, "Position jumped"),
             (FROZEN, "Position never moves"), (PERFECT, "Impossible accuracy"), (ROUNDED, "Typed-in coordinates")]
    INFO, WARNING, HIGH = "info", "warning", "high"
    SEVERITIES = [(INFO, "Info"), (WARNING, "Warning"), (HIGH, "High")]

    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="integrity_flags")
    attempt = models.ForeignKey("exams.Attempt", on_delete=models.CASCADE, related_name="integrity_flags")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=24, choices=KINDS)
    severity = models.CharField(max_length=8, choices=SEVERITIES, default=WARNING)
    count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    detail = models.JSONField(default=dict, blank=True)  # the latest evidence (device ids shortened, jump size, ...)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "kind"], name="pr_flag_attempt_kind")]
        indexes = [models.Index(fields=["exam", "acknowledged_at"], name="pr_flag_exam_ack")]


class StudentRelation(models.Model):
    """An administrator says two students are expected to be close together: twins, the same house, or the same room.
    When the system sees them close it draws a line with this label on the map and raises no alert and never locks them.
    One row per pair; `a` is always the student with the smaller id."""
    TWIN, HOUSE, ROOM = "twin", "house", "room"
    KINDS = [(TWIN, "Twins"), (HOUSE, "Same house"), (ROOM, "Same room")]

    a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=8, choices=KINDS, default=HOUSE)
    note = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["a", "b"], name="pr_relation_pair"),
                       models.CheckConstraint(condition=models.Q(a__lt=models.F("b")), name="pr_relation_ordered")]
        ordering = ["-created_at", "-id"]
