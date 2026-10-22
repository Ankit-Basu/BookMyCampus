"""
The background sweeper: auto-release no-shows, complete finished bookings, send reminders.

It runs in one of three places — whichever is available — and every run stamps
`Policy.last_sweep_at`, so the control room can show whether automation is alive:

* Celery Beat (production, Redis broker)          → apps.bookings.tasks
* `python manage.py run_scheduler` (separate process)
* in-process thread started by `runserver` when AUTO_SWEEP is on (default in DEBUG)
"""
import logging
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

log = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def sweep_once():
    from apps.rules.models import Policy

    from . import services

    released = services.auto_release_sweep()
    completed = services.complete_finished()
    reminded = services.send_reminders()
    Policy.objects.filter(pk=Policy.get().pk).update(last_sweep_at=timezone.now())
    return {"released": released, "completed": completed, "reminders": reminded}


def _loop(interval):
    time.sleep(3)  # let the server finish booting
    while True:
        try:
            result = sweep_once()
            if any(result.values()):
                log.info("sweeper: %s", result)
        except Exception:  # never let the thread die
            log.exception("sweeper run failed")
        finally:
            close_old_connections()
        time.sleep(interval)


def start_in_process(interval=30):
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(interval,), name="bmc-sweeper", daemon=True).start()
    log.info("in-process sweeper started (every %ss)", interval)
