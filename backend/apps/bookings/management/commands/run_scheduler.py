import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bookings import services


class Command(BaseCommand):
    help = "Run the auto-release / reminder / completion sweeps in a loop (Celery Beat alternative for local dev)."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=30)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, interval, once, **kw):
        self.stdout.write(self.style.SUCCESS(f"Sweeper running every {interval}s — Ctrl+C to stop"))
        while True:
            released = services.auto_release_sweep()
            done = services.complete_finished()
            reminded = services.send_reminders()
            if released or done or reminded:
                self.stdout.write(f"{timezone.localtime():%H:%M:%S} released={released} completed={done} reminders={reminded}")
            if once:
                return
            time.sleep(interval)
