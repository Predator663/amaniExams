"""Closes exams, auto-submits overdue attempts and publishes results (exam end + delay).

Run every minute, e.g. a Render cron job:   python manage.py run_scheduler
or as a worker:                              python manage.py run_scheduler --loop 20
The API also performs the same work lazily on each request, so a missed cron run cannot
leak or withhold results; this command just keeps statuses and notifications timely."""
import time

from django.core.management.base import BaseCommand

from exams.models import Exam
from exams.services import sync_exam
from gamification.services import reward_pending
from notifications.services import run_exam_notifications


class Command(BaseCommand):
    help = "Advance exam statuses, auto-submit overdue attempts, publish results."

    def add_arguments(self, parser):
        parser.add_argument("--loop", type=int, default=0, help="Repeat every N seconds (0 = run once).")

    def handle(self, *args, **opts):
        while True:
            n = 0
            for exam in Exam.objects.exclude(status__in=[Exam.DRAFT, Exam.PUBLISHED]):
                before = exam.status
                sync_exam(exam)
                if exam.status != before:
                    n += 1
                    self.stdout.write(f"exam {exam.pk} '{exam.title}': {before} -> {exam.status}")
            sent = run_exam_notifications()  # reminders (1 day, 1 hour), exam start
            if sent:
                self.stdout.write(f"{sent} notification(s) created")
            rewarded = reward_pending()  # XP, streaks and badges for published results (BR-10)
            if rewarded:
                self.stdout.write(f"{rewarded} exam reward(s) processed")
            if not opts["loop"]:
                break
            time.sleep(opts["loop"])
