from celery import shared_task

from . import services
from .sweeper import sweep_once


@shared_task
def auto_release_sweep():
    return services.auto_release_sweep()


@shared_task
def complete_finished():
    return services.complete_finished()


@shared_task
def send_reminders():
    return services.send_reminders()


@shared_task
def sweep():
    """One combined run (also stamps the heartbeat)."""
    return sweep_once()
