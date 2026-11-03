import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.bookings.sweeper import sweep_once


class Command(BaseCommand):
    help = "Run the auto-release / reminder / completion sweeps in a loop (Celery Beat alternative for local dev)."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=30)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, interval, once, **kw):
        self.stdout.write(self.style.SUCCESS(f"Sweeper running every {interval}s — Ctrl+C to stop"))
        while True:
            try:
                r = sweep_once()
                if any(r.values()):
                    self.stdout.write(f"{timezone.localtime():%H:%M:%S} released={r['released']} completed={r['completed']} reminders={r['reminders']}")
            except Exception as exc:
                if once:
                    raise
                # A database blip must not end the loop: auto-release would silently stop until a restart.
                self.stderr.write(f"Sweep failed, retrying in {interval}s: {exc}")
            if once:
                return
            close_old_connections()
            time.sleep(interval)
