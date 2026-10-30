from django.core.management.base import BaseCommand

from accounts import temp_password
from accounts.models import User


class Command(BaseCommand):
    help = ("Replace the OLD starting passwords (= index number) of students who never logged in with random ones, then print the "
            "credentials sheets again. Run once after upgrading. Add --yes to do it; without it only counts.")

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true")
        parser.add_argument("--include-sms", action="store_true",
                            help="also students whose password was sent to a parent by SMS (their SMS password stops working)")

    def handle(self, *a, yes=False, include_sms=False, **o):
        qs = User.objects.filter(role=User.Role.STUDENT, must_change_password=True, is_archived=False, temp_issued_at__isnull=True)
        users = list(qs)
        if not include_sms:
            from guardians.models import SmsJob  # students already texted a random password keep it
            texted = {sid for j in SmsJob.objects.filter(login=True).only("students") for sid in j.students}
            users = [u for u in users if u.pk not in texted]
        self.stdout.write(f"{len(users)} student(s) still on an old starting password.")
        if not yes:
            self.stdout.write("Nothing changed. Run again with --yes to issue new starting passwords.")
            return
        for u in users:
            temp_password.issue(u)
        self.stdout.write(self.style.SUCCESS("Done. Print the new sheets: Students -> Credentials (PDF/CSV)."))
