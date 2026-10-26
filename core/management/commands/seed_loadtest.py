"""Creates fake students, questions and one live exam for load testing (NFR-05, acceptance test 9.2).

    python manage.py seed_loadtest --students 500 --questions 40
    python manage.py seed_loadtest --cleanup            (removes everything this command made)

NEVER run this on the real school database. Use a separate test server and database.
Students are named lt0001, lt0002 ... with the password given by --password. They do not have to change it."""
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import SchoolClass, Subject
from accounts.models import User
from exams.models import Exam, ExamQuestion

CLASS_NAME, SUBJECT_NAME, EXAM_TITLE = "Load Test", "Load Test Subject", "Load Test Exam"


class Command(BaseCommand):
    help = "Create (or remove) load-test students and a live exam. Test servers only."

    def add_arguments(self, p):
        p.add_argument("--students", type=int, default=500)
        p.add_argument("--questions", type=int, default=40)
        p.add_argument("--prefix", default="lt")
        p.add_argument("--password", default="LoadTest-2026")
        p.add_argument("--start-in-minutes", type=int, default=0, help="0 = the exam is open right now")
        p.add_argument("--window-minutes", type=int, default=180)
        p.add_argument("--duration-minutes", type=int, default=60)
        p.add_argument("--cleanup", action="store_true")
        p.add_argument("--yes", action="store_true", help="I understand this is NOT the real school database")

    def handle(self, *a, **o):
        prefix = o["prefix"]
        if o["cleanup"]:
            return self.cleanup(prefix)
        if not o["yes"]:
            raise CommandError("This fills the database with fake students. Add --yes if this is a TEST server.")
        if o["students"] < 1 or o["questions"] < 1:
            raise CommandError("Use at least 1 student and 1 question.")
        with transaction.atomic():
            cls, _ = SchoolClass.objects.get_or_create(name=CLASS_NAME, stream="", defaults={"form_level": 1})
            subject, _ = Subject.objects.get_or_create(name=SUBJECT_NAME)
            hashed = make_password(o["password"], hasher="pbkdf2_sha256_initial")  # light hash: 500 accounts in seconds
            have = set(User.objects.filter(username__startswith=prefix).values_list("username", flat=True))
            new = []
            for i in range(1, o["students"] + 1):
                name = f"{prefix}{i:04d}"
                if name not in have:
                    new.append(User(username=name, first_name=f"Load{i}", last_name="Test", role=User.Role.STUDENT,
                                    index_number=f"LT{i:04d}", school_class=cls, password=hashed, must_change_password=False))
            User.objects.bulk_create(new, batch_size=200)
            start = timezone.now() + timedelta(minutes=o["start_in_minutes"])
            exam = Exam.objects.create(
                title=EXAM_TITLE, subject=subject, start_at=start, end_at=start + timedelta(minutes=o["window_minutes"]),
                duration_minutes=o["duration_minutes"], status=Exam.SCHEDULED, shuffle_questions=True, shuffle_options=True,
                rules_text="Load test.")
            exam.classes.add(cls)
            for pos in range(1, o["questions"] + 1):
                ExamQuestion.objects.create(exam=exam, position=pos, payload={
                    "qtype": "mcq_single", "prompt": f"Load test question {pos}: 2 + 2 = ?", "marks": 1, "topic": "Load",
                    "difficulty": "easy", "explanation": "4",
                    "content": {"options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}, {"id": "c", "text": "5"}, {"id": "d", "text": "6"}]},
                    "answer": {"correct": "b"}})
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(new)} new student(s) ({o['students']} in total), exam {exam.pk} with {o['questions']} questions."))
        self.stdout.write(f"Now run:  python loadtest/run_load.py --base-url https://YOUR-TEST-SERVER --students {o['students']} "
                          f"--prefix {prefix} --password '{o['password']}'")

    def cleanup(self, prefix):
        with transaction.atomic():
            Exam.objects.filter(title=EXAM_TITLE, subject__name=SUBJECT_NAME).delete()
            n = User.objects.filter(username__startswith=prefix, role=User.Role.STUDENT, school_class__name=CLASS_NAME).delete()[0]
            Subject.objects.filter(name=SUBJECT_NAME).delete()
            SchoolClass.objects.filter(name=CLASS_NAME, students__isnull=True).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed load-test data ({n} rows including related records)."))
