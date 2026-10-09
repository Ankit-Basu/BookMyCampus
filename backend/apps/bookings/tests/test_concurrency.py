"""
Acceptance criterion #1: 500 concurrent attempts on one slot yield exactly one booking.

Each attempt runs on its own thread with its own PostgreSQL connection, and a barrier releases all
of them at the same instant. No lock exists anywhere in the application code; the only thing
standing between 500 requests and 500 bookings is the EXCLUDE constraint.
"""
import os
import threading
from collections import Counter

from django.contrib.auth.hashers import make_password
from django.db import connection, connections
from django.test import TransactionTestCase

from apps.accounts.models import Role, User
from apps.bookings.exceptions import SlotConflict
from apps.bookings.models import Booking, BookingSlot
from apps.bookings.services import create_booking

from .factories import at, make_campus

ATTEMPTS = int(os.environ.get("BMC_CONCURRENCY", "500"))


class FiveHundredClicksTest(TransactionTestCase):
    def test_exactly_one_booking_survives(self):
        dept, _, lab, _ = make_campus()
        pw = make_password("x")
        User.objects.bulk_create(
            [User(username=f"racer{i}", password=pw, role=Role.STUDENT, department=dept) for i in range(ATTEMPTS)]
        )
        users = list(User.objects.filter(username__startswith="racer"))
        with connection.cursor() as c:
            c.execute("SHOW max_connections")
            max_conn = int(c.fetchone()[0])
        # One connection per thread. With a default Postgres (100) we run in waves; with the
        # docker-compose server (700) all 500 genuinely hit the database at the same moment.
        wave = min(ATTEMPTS, max_conn - 20)

        start, end = at(2, 10), at(2, 11)
        outcomes = Counter()
        lock = threading.Lock()

        def attempt(user, barrier):
            try:
                barrier.wait()
                create_booking(user, lab, start, end, title=f"race {user.username}")
                result = "booked"
            except SlotConflict:
                result = "conflict"
            except Exception as exc:  # pragma: no cover - surfaced in the assertion message
                result = f"error:{type(exc).__name__}:{exc}"
            finally:
                connections.close_all()
            with lock:
                outcomes[result] += 1

        for i in range(0, ATTEMPTS, wave):
            batch = users[i : i + wave]
            barrier = threading.Barrier(len(batch))
            threads = [threading.Thread(target=attempt, args=(u, barrier)) for u in batch]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        errors = {k: v for k, v in outcomes.items() if k.startswith("error")}
        self.assertFalse(errors, f"unexpected errors: {errors}")
        self.assertEqual(outcomes["booked"], 1, outcomes)
        self.assertEqual(outcomes["conflict"], ATTEMPTS - 1, outcomes)
        self.assertEqual(Booking.objects.filter(resource=lab, status__in=Booking.ACTIVE).count(), 1)
        self.assertEqual(BookingSlot.objects.filter(resource=lab).count(), 1)
