"""Go-live checklist (Phase 3). Run it on the REAL server before the pilot and again before go-live:

    python manage.py golive_check

Each line is PASS, WARN (think about it) or FAIL (fix before go-live). The command exits with an error if
anything FAILs, so it can also be used in a deployment script. It only reads; it never changes data."""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from accounts.models import User
from core import grading
from core.models import SchoolSettings
from exams.models import Exam
from questions.models import Question


class Command(BaseCommand):
    help = "Check that the system is ready for the pilot exam and go-live."

    def handle(self, *args, **opts):
        results = []

        def check(level, name, detail=""):
            results.append((level, name, detail))

        s = SchoolSettings.load()
        db = settings.DATABASES["default"]["ENGINE"]

        check("PASS" if not settings.DEBUG else "FAIL", "DEBUG is off", "Set DJANGO_DEBUG=0 on the server.")
        check("FAIL" if settings.SECRET_KEY == "dev-insecure-change-me" else "PASS", "Secret key is set",
              "Set DJANGO_SECRET_KEY to a long random value.")
        hosts = [h for h in settings.ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]
        check("PASS" if hosts else "FAIL", "Allowed hosts include the real web address", "Set DJANGO_ALLOWED_HOSTS.")
        check("PASS" if settings.SECURE_SSL_REDIRECT else "FAIL", "HTTPS redirect is on (NFR-07)", "Leave DJANGO_SSL_REDIRECT=1.")
        check("PASS" if "postgresql" in db else "FAIL", "Database is PostgreSQL (NFR-05, NFR-06)",
              "SQLite is for development only. Set DATABASE_URL to PostgreSQL.")
        redis = "redis" in settings.CACHES["default"]["BACKEND"].lower()
        check("PASS" if redis else "WARN", "Redis is used for the online counter and timers",
              "Set REDIS_URL. Without it each server process counts separately, so 'students online' is wrong with several workers.")
        check("PASS" if settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY else "WARN", "Push notifications are configured (NOT-02)",
              "Set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and install pywebpush, or students only get in-app notices.")
        persistent = bool(os.environ.get("MEDIA_ROOT"))
        check("PASS" if persistent else "WARN", "Question images are stored on a persistent disk (SRS section 8)",
              "Set MEDIA_ROOT to a persistent disk, or use object storage. A normal Render disk is wiped on each deploy.")
        from guardians.models import Guardian
        if Guardian.objects.exists():
            check("PASS" if settings.GUARDIAN_KEY else "FAIL", "GUARDIAN_KEY is set (parents' phone numbers are encrypted with it)",
                  "Set GUARDIAN_KEY and keep a copy somewhere safe. Without it the saved numbers cannot be read.")
        check("PASS" if settings.TIME_ZONE == "Africa/Dar_es_Salaam" else "FAIL", "Time zone is East Africa Time (NFR-10)")

        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        check("PASS" if not pending else "FAIL", "All migrations are applied", "Run: python manage.py migrate")

        check("PASS" if User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True).exists() else "FAIL",
              "A Super Admin account exists", "Run createsuperuser, then set its role to super_admin.")
        problems = grading.validate_scale(s.grade_scale)
        check("PASS" if not problems else "FAIL", "Grading scale is valid (4.11)", "; ".join(problems))
        check("WARN", "The school has confirmed the NECTA grading scale and pass mark (SRS section 10, question 2)",
              "This cannot be checked by the computer. Get the sign-off in writing.")
        check("PASS", f"School name: {s.school_name}")
        check("PASS" if s.result_delay_minutes == 5 else "WARN", f"Result delay is {s.result_delay_minutes} minute(s)",
              "The SRS default is 5 minutes (BR-06).")
        check("PASS" if s.rules_text.strip() else "WARN", "Default exam rules text is written", "Set it in settings (ADM-09).")

        students = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_archived=False)
        n = students.count()
        check("PASS" if n else "FAIL", f"{n} active student account(s)", "Upload students first (AUTH-02).")
        check("PASS" if not students.exclude(school_class__isnull=False).exists() else "WARN", "Every student is in a class",
              "Students without a class cannot be given exams by class or take part in a class leaderboard.")
        check("PASS" if User.objects.filter(role=User.Role.TEACHER, is_active=True).exists() else "WARN", "Teacher accounts exist")
        approved = Question.objects.filter(status=Question.APPROVED).count()
        check("PASS" if approved else "WARN", f"{approved} approved question(s)")
        practice = Question.objects.filter(status=Question.APPROVED, practice_eligible=True).count()
        check("PASS" if practice >= 5 else "WARN", f"{practice} practice-eligible question(s)",
              "Practice mode needs at least 5 per subject and form.")
        upcoming = Exam.objects.filter(status=Exam.SCHEDULED, start_at__gt=timezone.now()).count()
        check("PASS" if upcoming else "WARN", f"{upcoming} upcoming scheduled exam(s)", "Schedule the pilot exam (ADM-07).")
        check("WARN", "The scheduler runs every minute (python manage.py run_scheduler)",
              "This cannot be checked from here. Confirm the Render cron job exists and succeeds.")
        check("WARN", "Daily backups and a tested restore exist (NFR-06)", "Do a restore test and write down the steps.")
        check("WARN", "A load test passed on the real server (NFR-05)", "See loadtest/README.md. Run it BEFORE go-live.")

        marks = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}
        fails = 0
        for level, name, detail in results:
            line = f"[{marks[level]}] {name}"
            if level != "PASS" and detail:
                line += f"\n         -> {detail}"
            style = {"PASS": self.style.SUCCESS, "WARN": self.style.WARNING, "FAIL": self.style.ERROR}[level]
            self.stdout.write(style(line))
            fails += level == "FAIL"
        warns = sum(1 for r in results if r[0] == "WARN")
        self.stdout.write(f"\n{len(results) - fails - warns} passed, {warns} to think about, {fails} to fix.")
        if fails:
            raise CommandError(f"{fails} check(s) failed. Fix them before go-live.")
