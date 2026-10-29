from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from exams.models import Attempt
from proctoring.models import IntegrityFlag, LiveLocation


class Command(BaseCommand):
    help = ("Delete the stored positions of finished exam attempts (privacy: positions are kept only while an exam is running, plus a "
            "short grace period). Alert records keep the closest-moment snapshot for the review. Run daily, e.g. from cron.")

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24, help="grace period after an attempt ends (default 24)")
        parser.add_argument("--flag-days", type=int, default=180, help="delete device / fake-position flags older than this many days (default 180)")

    def handle(self, *a, **o):
        cutoff = timezone.now() - timedelta(hours=o["hours"])
        n, _ = LiveLocation.objects.exclude(attempt__status=Attempt.IN_PROGRESS).filter(updated_at__lt=cutoff).delete()
        self.stdout.write(f"Removed {n} stored positions.")
        f, _ = IntegrityFlag.objects.filter(last_seen__lt=timezone.now() - timedelta(days=o["flag_days"])).delete()
        self.stdout.write(f"Removed {f} old integrity flags.")
