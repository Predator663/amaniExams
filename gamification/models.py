from django.conf import settings
from django.db import models

AVATARS = ["owl", "lion", "giraffe", "zebra", "elephant", "flamingo", "star", "rocket", "book", "sun", "tree", "flower"]


class GamificationSettings(models.Model):
    """Singleton row (pk=1). Admin-editable XP values, levels, badge targets and limits (ADM-09).
    Empty values mean 'use the defaults from the SRS', so a fresh install needs no setup."""

    xp_values = models.JSONField(default=dict, blank=True)    # only the values an admin changed
    levels = models.JSONField(default=list, blank=True)       # [] = the SRS 5.2 levels
    badge_tiers = models.JSONField(default=dict, blank=True)  # {badge code: [bronze, silver, gold]}
    freezes_per_month = models.PositiveSmallIntegerField(default=2)  # SRS 5.3
    practice_daily_xp_quizzes = models.PositiveSmallIntegerField(default=5)  # practice quizzes per day that earn XP

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Profile(models.Model):
    """A student's gamification profile (SRS 5.6). Created the first time it is needed."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gamification")
    avatar = models.CharField(max_length=20, default="owl")  # one of AVATARS (no photo uploads, so nothing to moderate)
    display_name = models.CharField(max_length=30, blank=True)  # shown to classmates; empty = "Amina K."
    hide_from_leaderboard = models.BooleanField(default=False)  # each student can hide herself
    last_seen_level = models.PositiveSmallIntegerField(default=1)  # drives the level-up celebration


class XPEvent(models.Model):
    """The XP ledger. Append-only in practice: a student's XP is the sum of her events.
    `key` makes every award idempotent (for example 'score:12'), so running a job twice never pays twice."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xp_events")
    kind = models.CharField(max_length=20)  # submit, early, score, improve, perfect, review, practice, streak
    points = models.IntegerField()
    key = models.CharField(max_length=80)
    exam_id = models.PositiveIntegerField(null=True, blank=True)  # a plain number: the ledger outlives a deleted exam
    detail = models.JSONField(default=dict, blank=True)  # values for the label, e.g. {"percent": 80}
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"], name="gam_xp_user_time")]
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="gam_xp_once")]


class ActivityDay(models.Model):
    """A day on which the student did meaningful learning (SRS 5.3). Streaks are worked out from these."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_days")
    day = models.DateField()  # East Africa Time
    source = models.CharField(max_length=10)  # exam, practice, review

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "day"], name="gam_one_day")]


class ExamRewardMark(models.Model):
    """Proof that a student's rewards for one exam were handed out (so it happens exactly once)
    and a record of what that exam earned her (RES-03)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reward_marks")
    exam_id = models.PositiveIntegerField()
    processed_at = models.DateTimeField(auto_now_add=True)
    badges = models.JSONField(default=list, blank=True)  # badges newly earned in this step: [{"code", "scope", "tier"}]

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "exam_id"], name="gam_mark_once")]


class BadgeAward(models.Model):
    """The highest tier a student holds of one badge. `scope` is the subject id for Subject Star, else ''."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges")
    code = models.CharField(max_length=30)
    scope = models.CharField(max_length=20, blank=True, default="")
    tier = models.PositiveSmallIntegerField(default=1)  # 1 bronze, 2 silver, 3 gold
    awarded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    seen = models.BooleanField(default=False)  # false until the student has seen the unlock animation

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["user", "code", "scope"], name="gam_badge_once")]


class ReviewProgress(models.Model):
    """Which wrong answers a student has looked at in review mode (Mistake Master, +XP)."""

    attempt = models.OneToOneField("exams.Attempt", on_delete=models.CASCADE, related_name="review_progress")
    seen = models.JSONField(default=list, blank=True)  # question numbers she has viewed
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)


class PracticeSession(models.Model):
    """One practice quiz (SRS 5.5). Never counts toward exam marks and never touches Result.
    `items` keeps a private copy of the questions, with answers, on the server only."""

    IN_PROGRESS, COMPLETED, ABANDONED = "in_progress", "completed", "abandoned"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practice_sessions")
    subject = models.ForeignKey("academics.Subject", on_delete=models.CASCADE, related_name="practice_sessions")
    items = models.JSONField(default=list)    # [{"qid": 3, "payload": {...}}]
    answers = models.JSONField(default=list, blank=True)  # [{"qid": 3, "response": ..., "fraction": 1.0}]
    seed = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, default="in_progress")
    question_count = models.PositiveSmallIntegerField(default=0)  # how many questions this quiz has
    correct_score = models.FloatField(default=0)  # sum of the fractions correct
    xp_awarded = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "status"], name="gam_prac_user_status")]
