from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from controlroom import state
from controlroom.models import ControlEvent, SiteControl


class Command(BaseCommand):
    help = "Emergency switch from the server shell:  python manage.py maintenance on|off|status  [--message TEXT] [--back-at TEXT]"

    def add_arguments(self, p):
        p.add_argument("action", choices=["on", "off", "status"])
        p.add_argument("--message", default="")
        p.add_argument("--back-at", default="")

    def handle(self, *a, action, message, back_at, **o):
        ctl = SiteControl.get()
        if action == "status":
            self.stdout.write("MAINTENANCE ON" if ctl.maintenance else "online")
            return
        ctl.maintenance = action == "on"
        if ctl.maintenance:
            ctl.started_at, ctl.started_by, ctl.message, ctl.back_at = timezone.now(), "shell", message[:300], back_at[:80]
        ctl.save()
        state.reset_cache()
        ControlEvent.objects.create(who="shell", action="maintenance_" + action, detail=f"message={message[:300]!r} back_at={back_at[:80]!r}" if ctl.maintenance else "")
        self.stdout.write(self.style.WARNING("Maintenance is now ON") if ctl.maintenance else self.style.SUCCESS("Site is online"))
