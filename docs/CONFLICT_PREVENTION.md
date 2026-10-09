# How BookMyCampus makes double-booking impossible

> The required artefact for P20 · Track P: a written explanation of the
> conflict-prevention mechanism, and why it works.

## The problem with "check, then book"

The obvious implementation is:

```python
if not Booking.objects.filter(resource=r, period__overlap=(start, end)).exists():
    Booking.objects.create(resource=r, period=(start, end))
```

This is a race. Two requests run the `exists()` check at the same moment, both see an empty
slot, and both insert. Adding locks in Python moves the problem around. The lock must be held
across processes and servers, released on every failure path, and every code path that writes a
booking has to remember to take it. When a lab slot opens and 500 students click at once, any gap
in that discipline becomes a double booking.

## The fix: let PostgreSQL refuse the second row

Each booking stores its time as a **range** (`tstzrange`, Django's `DateTimeRangeField`), and the
table carries an **exclusion constraint**:

```python
ExclusionConstraint(
    name="booking_no_overlap",
    expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
    condition=Q(status__in=["pending", "confirmed", "checked_in"]),
)
```

which becomes

```sql
ALTER TABLE bookings_booking ADD CONSTRAINT booking_no_overlap
  EXCLUDE USING gist (resource_id WITH =, period WITH &&)
  WHERE (status IN ('pending', 'confirmed', 'checked_in'));
```

The constraint means: no two rows may have an equal `resource_id` **and** overlapping `period`. The
database checks it on every insert and update, inside the same index operation that stores the
row. That makes it atomic with respect to every other transaction, whatever code wrote the row:
the API, the Django admin, a shell script or a raw SQL `INSERT`.

* `btree_gist` is installed (first operation in `bookings/0001_initial.py`) so a GiST index can
  compare the scalar `resource_id` with `=` alongside the range `&&`.
* Ranges are half-open, `[start, end)`. A 10:00–11:00 booking and an 11:00–12:00 booking *touch*
  but do not *overlap*, so back-to-back slots work naturally.
* The `WHERE` clause makes cancelled, rejected, released and completed bookings stop holding the
  slot. Flipping a status frees the time with no extra bookkeeping.

### Not just bookings: one ledger for everything that occupies a room

A booking must also be impossible over a **timetabled lecture** or a **maintenance window**. So
there is a second table, `BookingSlot`, which is the occupancy ledger. Every live occupancy writes
a row into it:

| kind          | written by                                   | removed when                      |
|---------------|----------------------------------------------|-----------------------------------|
| `booking`     | the booking engine, in the same transaction  | cancel / reject / release / finish |
| `timetable`   | `timetable.services.publish` (from P13)      | the next publication replaces it  |
| `maintenance` | `maintenance.services.schedule`              | resolve / cancel                  |

`BookingSlot` carries the same `EXCLUDE USING gist (resource_id WITH =, period WITH &&)`
constraint, with no condition. So:

* A room teaching CSE326 at 10:00 has a `timetable` row from 10:00 to 10:50. A booking for 10:30
  fails the insert of its slot row and is rolled back. "Timetable-occupied slots are never offered"
  holds at the database, not only in the UI.
* The availability API reads the same ledger to draw the calendar, so the UI and the guarantee
  agree by construction.

## The booking path, step by step

`apps/bookings/services.py::create_booking`

1. **Policy** (`rules.services.validate_request`): opening hours, duration, notice, booking
   window, blackouts, role permissions, capacity, the no-show restriction. These decide whether
   you may *ask*. They never decide whether the slot is free.
2. **Quota** (inside the transaction, after `SELECT … FOR UPDATE` on the user row). Weekly hours
   are summed and compared. The row lock serialises one user's concurrent requests so a quota
   can't be overshot by double-clicking. It is unrelated to slot correctness.
3. **Claim** (inside a savepoint): `INSERT` into `Booking`, then `INSERT` into `BookingSlot`.
4. If PostgreSQL raises `SQLSTATE 23P01 exclusion_violation`, the savepoint rolls back and the
   API returns **409 Conflict**, saying what is in the way (another booking, a class, maintenance).
5. If PostgreSQL raises `SQLSTATE 40P01 deadlock_detected`, the request is retried (see below).

The application never checks "is it free?" before writing. It just tries to write.

### The deadlock case

Under extreme contention, two transactions can insert overlapping rows at the same instant. Each
inserts its index entry, finds the other's *uncommitted* conflicting entry, and waits for it to
commit or abort. They are now waiting for each other. PostgreSQL detects this and aborts one with
`40P01`. Correctness is unaffected: neither row was committed, and the survivor proceeds. The
engine rolls back the savepoint and retries with jitter. The retry then sees the winner's
committed row and gets a clean `23P01 → 409`. The 500-way test exercises this path.

## Proof

`backend/apps/bookings/tests/test_concurrency.py`

* Creates 500 distinct student accounts.
* Starts 500 threads, **each with its own PostgreSQL connection**. A `threading.Barrier` releases
  all of them at the same moment.
* Every thread calls `create_booking` for the same lab, 10:00–11:00.
* Asserts **exactly 1** booking succeeded, **499** got `SlotConflict`, there were no other errors,
  and exactly one live `Booking` row and one `BookingSlot` row exist.

The docker-compose PostgreSQL runs with `max_connections=700`, so all 500 attempts really are
simultaneous. Against a default server (100 connections), the test runs the 500 attempts in
waves that fit.

```
python manage.py test apps.bookings.tests.test_concurrency
```

`test_engine.py` also shows the guarantee without the service layer: a raw
`Booking.objects.create` of an overlapping row raises `IntegrityError`.

## Why this is better than a Redis lock (Track J's approach)

| | Redis lock + unique index | PostgreSQL exclusion constraint |
|---|---|---|
| Arbitrary ranges (10:15–11:40) | needs discrete timeslot rows | native |
| Holds for writes outside the API | no | yes |
| Must be released on every failure path | yes | nothing to release |
| Extra moving part on the critical path | Redis | none |
| Covers timetable + maintenance | separate checks | same ledger, same constraint |

Redis is still used, but only as the Celery broker for background sweeps (auto-release,
reminders, snapshots). If Redis goes down, booking correctness is unaffected.
