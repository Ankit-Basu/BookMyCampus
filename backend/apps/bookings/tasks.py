from celery import shared_task

from . import services


@shared_task
def auto_release_sweep():
    return services.auto_release_sweep()


@shared_task
def complete_finished():
    return services.complete_finished()


@shared_task
def send_reminders():
    return services.send_reminders()
