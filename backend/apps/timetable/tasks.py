import json
import logging
from urllib.request import Request, urlopen

from celery import shared_task
from django.conf import settings

from .services import publish

log = logging.getLogger(__name__)


@shared_task
def refresh_timetable():
    """Pull the published timetable from P13. Idempotent: unchanged payloads are ignored by checksum."""
    url = settings.TIMETABLE_SOURCE_URL
    if not url:
        return "no source configured"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=20) as resp:  # noqa: S310 - URL is operator-configured
        payload = json.loads(resp.read())
    version, changed = publish(payload, source=url)
    log.info("timetable refresh: %s (changed=%s)", version.label, changed)
    return changed
