from django.conf import settings
from django.db import models
from django.db.models import Q


class Exam(models.Model):
    DRAFT, SCHEDULED, LIVE, CLOSED, PUBLISHED = "draft", "scheduled", "live", "closed", "published"
    STATUSES = [(DRAFT, "Draft"), (SCHEDULED, "Scheduled"), (LIVE, "Live"), (CLOSED, "Closed"),
                (PUBLISHED, "Results published")]  # EXM-07

    title = models.CharField(max_length=200)
    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="exams")
    term = models.ForeignKey("academics.Term", null=True, blank=True, on_delete=models.SET_NULL, related_name="exams")  # ADM-04
    classes = models.ManyToManyField("academics.SchoolClass", blank=True, related_name="exams")
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="individual_exams")  # EXM-06
    start_at = models.DateTimeField(null=True, blank=True)  # BR-09: entered manually by an admin
    end_at = models.DateTimeField(null=True, blank=True)  # a teacher's draft has no dates until an admin sets them
    duration_minutes = models.PositiveIntegerField(default=60)
    pass_mark_percent = models.FloatField(default=30)
    rules_text = models.TextField(blank=True)
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    allow_skip = models.BooleanField(default=False)
    late_entry_minutes = models.PositiveIntegerField(null=True, blank=True)  # null = school default
    time_warnings = models.JSONField(default=list)  # minutes before end; [] = default [10, 5, 1]
    partial_marks = models.BooleanField(default=True)  # EXM-05
    negative_marking = models.BooleanField(default=False)
    negative_fraction = models.FloatField(default=0.25)  # share of a question's marks deducted when wrong
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    # When a teacher hands a finished paper to the administrators for scheduling (a draft stays a draft until an admin
    # sets the date and classes). Kept after scheduling so the admin console can still show who submitted what and when.
    submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")

    class Meta:
        ordering = ["start_at"]

    @property
    def total_marks(self):
        return round(sum(q.payload["marks"] for q in self.questions.all() if not q.voided), 2)


class ExamQuestion(models.Model):
    """EXM-01 / QB-11: each exam keeps its own copy of every question it uses."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveIntegerField()
    source = models.ForeignKey("questions.Question", null=True, on_delete=models.SET_NULL)
    payload = models.JSONField()  # qtype, prompt, content, answer, marks, explanation, topic, difficulty
    voided = models.BooleanField(default=False)  # EXM-08
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["position"]
        unique_together = [("exam", "position")]


class Attempt(models.Model):
    IN_PROGRESS, SUBMITTED, AUTO_SUBMITTED = "in_progress", "submitted", "auto_submitted"

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    attempt_no = models.PositiveSmallIntegerField(default=1)  # BR-04: >1 only through an admin retake grant
    status = models.CharField(max_length=14, default=IN_PROGRESS)
    started_at = models.DateTimeField()
    deadline_at = models.DateTimeField()  # BR-03: the server owns the clock
    submitted_at = models.DateTimeField(null=True, blank=True)
    order = models.JSONField(default=list)  # ExamQuestion ids in this student's order
    current_index = models.PositiveIntegerField(default=0)
    seed = models.PositiveIntegerField(default=0)
    # Lock for leaving the exam screen too often, or by hand from the live monitor. "" = not locked.
    # The exam clock keeps running while locked. An unlock moves `leaves_forgiven` up to the number of exits so far,
    # so the student starts again with a full allowance instead of being locked by her very next exit.
    LOCK_LEAVES, LOCK_MANUAL = "leaves", "manual"
    screen_lock = models.CharField(max_length=10, blank=True, default="")  # "" | leaves | manual
    screen_locked_at = models.DateTimeField(null=True, blank=True)
    leaves_forgiven = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "student", "attempt_no"], name="one_attempt_per_no")]
        indexes = [models.Index(fields=["exam", "status"])]


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    exam_question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name="answers")
    response = models.JSONField(null=True, blank=True)
    skipped = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)
    marks_awarded = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = [("attempt", "exam_question")]


class Result(models.Model):
    attempt = models.OneToOneField(Attempt, on_delete=models.CASCADE, related_name="result")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="results")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="results")
    score = models.FloatField()
    total = models.FloatField()
    percent = models.FloatField()
    grade = models.CharField(max_length=2)
    points = models.PositiveSmallIntegerField()
    passed = models.BooleanField(default=False)
    scale_snapshot = models.JSONField()  # GRD-04: the scale in force when marked
    time_taken_seconds = models.PositiveIntegerField(default=0)
    topic_stats = models.JSONField(default=dict)  # {topic: [earned, possible]}  (RES-04)

    class Meta:
        indexes = [models.Index(fields=["exam", "-score"])]


class ExamGrant(models.Model):
    """EXM-09: extra time or a retake for one student, always audited with a reason."""

    EXTRA_TIME, RETAKE = "extra_time", "retake"
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="grants")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=10)
    extra_minutes = models.PositiveIntegerField(default=0)
    reason = models.CharField(max_length=300)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AttemptEvent(models.Model):
    """EDAY-11: integrity info flags (tab switches). Information only, never an accusation."""

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20)  # left_screen | returned
    at = models.DateTimeField(auto_now_add=True)
