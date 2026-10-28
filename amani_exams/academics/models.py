from django.conf import settings
from django.db import models


class SchoolClass(models.Model):
    name = models.CharField(max_length=40)  # e.g. "Form 1"
    form_level = models.PositiveSmallIntegerField(default=1)  # 1-4 (O-Level)
    stream = models.CharField(max_length=20, blank=True)

    class Meta:
        unique_together = [("name", "stream")]
        ordering = ["form_level", "name", "stream"]

    def __str__(self):
        return f"{self.name} {self.stream}".strip()


class Subject(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=20, blank=True)
    language = models.CharField(max_length=2, default="en")  # examined language (question 3 in SRS 10)
    practice_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TeacherAssignment(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="assignments")
    school_class = models.ForeignKey(SchoolClass, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("teacher", "subject", "school_class")]


class AcademicYear(models.Model):
    """ADM-04."""

    name = models.CharField(max_length=20, unique=True)  # e.g. "2026"
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-name"]

    def __str__(self):
        return self.name


class Term(models.Model):
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=40)  # e.g. "Term 1"
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        unique_together = [("year", "name")]
        ordering = ["-year__name", "start_date"]

    def __str__(self):
        return f"{self.year.name} {self.name}"
