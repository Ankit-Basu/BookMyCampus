import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .models import Notification

log = logging.getLogger(__name__)


def notify(user, kind, title, body="", booking=None, link="", email=True):
    """Create an in-app notification and (after commit) send the matching email."""
    if user is None:
        return None
    n = Notification.objects.create(user=user, kind=kind, title=title, body=body, booking=booking, link=link)
    if email and user.email:
        url = f"{settings.FRONTEND_URL}{link}" if link else settings.FRONTEND_URL

        def _send():
            try:
                send_mail(f"[BookMyCampus] {title}", f"{body}\n\n{url}", None, [user.email], fail_silently=True)
            except Exception:  # pragma: no cover - mail must never break booking
                log.exception("notification email failed")

        transaction.on_commit(_send)
    return n


def notify_many(users, *args, **kwargs):
    seen = set()
    for u in users:
        if u and u.pk not in seen:
            seen.add(u.pk)
            notify(u, *args, **kwargs)
