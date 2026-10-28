from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


THEMES = {"light", "dark", "high_contrast", "colour_blind", "soft"}  # ACC-01


class AmaniUserManager(UserManager):
    """`manage.py createsuperuser` must make a real Super Admin. Without this the account gets the default
    role (student) and the web app treats it as a student even though it can open /django-admin/."""

    def create_superuser(self, username, email=None, password=None, **extra):
        extra.setdefault("role", "super_admin")
        return super().create_superuser(username, email, password, **extra)


class User(AbstractUser):
    objects = AmaniUserManager()

    class Role(models.TextChoices):
        STUDENT = "student"
        TEACHER = "teacher"
        ADMIN = "admin"
        SUPER_ADMIN = "super_admin"

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.STUDENT)
    index_number = models.CharField(max_length=40, blank=True, db_index=True)
    school_class = models.ForeignKey(
        "academics.SchoolClass", null=True, blank=True, on_delete=models.SET_NULL, related_name="students"
    )
    must_change_password = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)  # ADM-01: delete = archive, restorable
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=2, default="en")
    theme = models.CharField(max_length=20, default="light")
    graduated = models.BooleanField(default=False)  # ADM-01
    # Accessibility preferences (ACC-02, ACC-03, ACC-06); the app reads these and applies them.
    text_size = models.PositiveSmallIntegerField(default=100)  # percent, 100-200
    line_spacing = models.FloatField(default=1.5)
    dyslexia_font = models.BooleanField(default=False)
    reduce_motion = models.BooleanField(default=False)
    read_aloud = models.BooleanField(default=False)

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin_role(self):
        return self.role in (self.Role.ADMIN, self.Role.SUPER_ADMIN)

    @property
    def is_staff_role(self):
        return self.role != self.Role.STUDENT


class BulkUploadBatch(models.Model):
    PENDING, CONFIRMED = "pending", "confirmed"
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    rows = models.JSONField(default=list)  # validated rows waiting for confirmation
    report = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default=PENDING)
    created_user_ids = models.JSONField(default=list)
