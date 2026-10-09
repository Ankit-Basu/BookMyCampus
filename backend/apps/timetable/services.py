"""
Timetable integration (P13). The published timetable is a *hard* constraint: each class occurrence
is written into the occupancy ledger (BookingSlot), so the same exclusion constraint that stops
double-booking also stops anyone booking over a lecture. Republication swaps the whole set
atomically and displaces any bookings the new timetable now collides with.
"""
import hashlib
import json
from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.exceptions import BookingError, is_exclusion_violation
from apps.bookings.models import BookingSlot
from apps.bookings.services import displace, tsrange
from apps.catalogue.models import Resource

from .models import TimetableEntry, TimetableVersion


def _parse_time(v):
    return v if isinstance(v, time) else time.fromisoformat(v)


def _parse_date(v):
    return v if isinstance(v, date) else date.fromisoformat(v)


def checksum(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def validate_payload(payload):
    entries = payload.get("entries") or []
    codes = {e["resource_code"] for e in entries}
    resources = {r.code: r for r in Resource.objects.filter(code__in=codes)}
    missing = sorted(codes - resources.keys())
    if missing:
        raise BookingError("unknown_resources", f"Timetable references unknown rooms: {', '.join(missing)}", {"missing": missing})
    # Clash inside the timetable itself → reject the publication with a precise message.
    by_key = {}
    for e in entries:
        by_key.setdefault((e["resource_code"], int(e["weekday"])), []).append(e)
    for (code, wd), items in by_key.items():
        items.sort(key=lambda x: _parse_time(x["start"]))
        for a, b in zip(items, items[1:]):
            if _parse_time(b["start"]) < _parse_time(a["end"]):
                raise BookingError(
                    "timetable_clash",
                    f"Timetable double-books {code} on day {wd}: {a['course_code']} and {b['course_code']}.",
                )
    return resources


def publish(payload, source="manual"):
    """
    payload = {label, term_start, term_end, entries: [{resource_code, weekday, start, end,
               course_code, course_name?, section?, faculty?}]}
    Idempotent: re-publishing an identical payload is a no-op.
    """
    digest = checksum(payload)
    current = TimetableVersion.objects.filter(is_current=True).first()
    if current and current.checksum == digest:
        return current, False

    resources = validate_payload(payload)
    term_start, term_end = _parse_date(payload["term_start"]), _parse_date(payload["term_end"])
    tz = timezone.get_current_timezone()

    with transaction.atomic():
        TimetableVersion.objects.filter(is_current=True).update(is_current=False)
        BookingSlot.objects.filter(kind=BookingSlot.Kind.TIMETABLE).delete()
        version = TimetableVersion.objects.create(
            label=payload.get("label") or f"Timetable {timezone.localdate():%d %b %Y}",
            source=source, term_start=term_start, term_end=term_end, is_current=True, checksum=digest,
        )
        displaced = 0
        slots = []
        for e in payload["entries"]:
            entry = TimetableEntry.objects.create(
                version=version, resource=resources[e["resource_code"]], weekday=int(e["weekday"]),
                start_time=_parse_time(e["start"]), end_time=_parse_time(e["end"]),
                course_code=e["course_code"], course_name=e.get("course_name", ""),
                section=e.get("section", ""), faculty_name=e.get("faculty", ""),
            )
            d = term_start + timedelta(days=(entry.weekday - term_start.weekday()) % 7)
            label = f"{entry.course_code}{' · ' + entry.section if entry.section else ''}"
            while d <= term_end:
                s = timezone.make_aware(datetime.combine(d, entry.start_time), tz)
                en = timezone.make_aware(datetime.combine(d, entry.end_time), tz)
                if en > timezone.now():
                    displaced += displace(entry.resource, s, en, f"the timetable now schedules {label} here")
                slots.append(
                    BookingSlot(resource=entry.resource, period=tsrange(s, en), kind=BookingSlot.Kind.TIMETABLE,
                                timetable_entry=entry, label=label)
                )
                d += timedelta(days=7)
        try:
            BookingSlot.objects.bulk_create(slots, batch_size=1000)
        except IntegrityError as exc:
            if is_exclusion_violation(exc):
                raise BookingError("timetable_conflict", "Timetable collides with maintenance or another occupancy.", http_status=409) from None
            raise
        version.displaced_bookings = displaced
        version.save(update_fields=["displaced_bookings"])
    return version, True
