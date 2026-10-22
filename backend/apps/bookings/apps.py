import os
import sys

from django.apps import AppConfig
from django.conf import settings


class BookingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bookings'

    def ready(self):
        # Under `runserver` the autoreloader runs the app in a child process with RUN_MAIN=true;
        # start the sweeper only there (once), never during tests, migrations or shell sessions.
        if not settings.AUTO_SWEEP or "runserver" not in sys.argv:
            return
        if os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv:
            from .sweeper import start_in_process

            start_in_process(settings.AUTO_SWEEP_INTERVAL)
