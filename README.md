# BookMyCampus · LPU

**One booking system for every bookable resource at Lovely Professional University**: classrooms,
labs, high-value instruments, seminar halls, sports facilities, meeting rooms and vehicles. It has
availability rules, approval chains, QR check-in, auto-release of no-shows, timetable-aware
availability and utilisation analytics.

> P20 · Campus Resource, Lab and Facility Booking Platform. **Track P: Django + PostgreSQL**, with a
> React frontend.

The core guarantee, **zero double-bookings**, is enforced by a PostgreSQL exclusion constraint,
not by application locks. The test suite fires 500 simultaneous attempts at one slot and asserts
exactly one booking exists. → [docs/CONFLICT_PREVENTION.md](docs/CONFLICT_PREVENTION.md)

---

## Quick start

Prerequisites: Python 3.12+, Node 20+, Docker Desktop.

```bash
# 1. Database + Redis
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo --reset   # realistic LPU campus + 4 weeks of history (~1 min)
python manage.py runserver 127.0.0.1:8000

# 3. Background sweeps (auto-release, reminders) — pick one
python manage.py run_scheduler       # simple loop, good for local dev / Windows
celery -A config worker -B -l info   # production-style, uses Redis

# 4. Frontend
cd ../frontend
npm install
npm run dev                          # http://localhost:5173
```

### Demo personas (password `campus123`)

The login screen has one-click buttons for each.

| UMS ID | Role | Try this |
|---|---|---|
| `demo.student` | Student · CSE | Has a booking that's live **right now**: open *My bookings* and check in from *Scan* |
| `demo.faculty` | Faculty · CSE | Recurring weekly booking; book on behalf of a class (K22CS-B) |
| `demo.custodian` | Custodian | Approval queue, check-in posters, maintenance, consumables |
| `demo.head` | Head of Dept · CSE | Seminar-hall approvals, department utilisation |
| `demo.manager` | Facility Manager | Control room: analytics, policy, workflows, timetable |
| `demo.admin` | Administrator | Everything, plus Django admin at `/django-admin/` |

---

## What's in it

| Module | Where | Highlights |
|---|---|---|
| **M1 Resource catalogue** | `apps/catalogue` | Types, attributes, photos, capacity, features, custodians, LPU block locations; faceted search; CSV bulk import; printable QR door posters |
| **M2 Availability & rules** | `apps/rules` | Opening hours per type or per resource, min/max duration, notice period, booking window, blackouts, department/role/user quotas, runtime-editable policy |
| **M3 Booking engine** | `apps/bookings` | Atomic slot claim via `EXCLUDE USING gist`, 409 with the reason (class / maintenance / taken), recurring series with per-occurrence conflict handling (skip or all-or-nothing) |
| **M4 Timetable integration** | `apps/timetable` | P13 webhook (`X-Timetable-Token`) or pull (`TIMETABLE_SOURCE_URL`); classes written into the occupancy ledger; idempotent republish displaces newly-clashing bookings |
| **M5 Approval workflow** | `apps/approvals` | Chains by resource type × requester role (custodian → HoD → facility manager); visual builder; approve a whole series in one click |
| **M6 Check-in & auto-release** | `apps/bookings` | Scan the room poster *or* the custodian scans your pass; 15-min grace; auto-release sweep; progressive no-show restriction (warn → 7-day pause → 30-day pause); early check-out hands time back |
| **M7 Maintenance** | `apps/maintenance` | Scheduled windows + one-tap breakdown reports; displaces affected bookings and notifies them; downtime tracking |
| **M8 Consumables** | `apps/consumables` | Stock with oversell-proof atomic decrement, issue with booking, returns, low-stock alerts |
| **M9 Analytics** | `apps/analytics` | Utilisation by resource/type/department/day, idle-value ranking, weekday×hour heatmap, no-show rates, demand vs supply, approval turnaround, downtime, quota consumption, nightly snapshots |
| Notifications | `apps/notifications` | In-app bell + email for every lifecycle event |
| Calendar sync | `/api/calendar/<token>.ics` | Personal iCal feed for Google / Outlook / Apple; per-booking `.ics` |

### Acceptance criteria → evidence

| Criterion | Evidence |
|---|---|
| 500 concurrent attempts → exactly one booking | `apps/bookings/tests/test_concurrency.py` |
| Timetable-occupied slots never offered | `TimetableTest.test_timetabled_slot_never_offered`, `test_cannot_book_over_lecture` |
| Workflows configurable per type without deployment | Control room → Rules & workflows (`/api/workflows`) |
| QR check-in on mobile; auto-release after grace | `/scan` page; `CheckInAndReleaseTest` |
| No-show tracking + progressive restriction | `test_progressive_restriction`; Control room → Operations → No-show monitor |
| Utilisation + idle capacity across ≥ 3 types | Control room → Analytics (7 types seeded) |
| Recurring bookings with per-occurrence conflicts | `RecurringTest` (skip + all-or-nothing) |

```bash
cd backend && python manage.py test apps.bookings     # 27 tests, includes the 500-way race
```

### API (selection)

```
POST /api/auth/login                     GET  /api/resources?q=&type=&building=&free_from=&free_to=
GET  /api/resources/:id/availability     GET  /api/resources/:id/qr          (door poster SVG)
POST /api/bookings                       POST /api/bookings/:id/approve | reject
POST /api/bookings/:id/check-in          POST /api/bookings/scan              (mobile scanner)
POST /api/bookings/:id/check-out|cancel  GET  /api/bookings/:id/ics
GET  /api/maintenance  POST /api/maintenance  POST /api/maintenance/report
POST /api/timetable/publish              GET  /api/analytics/utilisation | heatmap | noshows | demand
```

---

## Stack & design

* **Backend:** Django 5.2, DRF, SimpleJWT, PostgreSQL 16 range types + `btree_gist`, Celery Beat on
  Redis (sweeps only), `qrcode`, `ics`.
* **Frontend:** React 19 + Vite + TypeScript, TanStack Query, FullCalendar (drag-to-select),
  GSAP ScrollTrigger + Lenis smooth scrolling, Motion, Leaflet (LPU campus map on OpenStreetMap),
  Recharts, html5-qrcode, and React Bits components (Aurora, Threads, Dock, SpotlightCard,
  GlareHover, ScrollVelocity, Magnet, ClickSpark, Noise and more).
* **Visual language:** "night campus box office". Frosted-glass panes over an ink sky, LPU-orange
  accents, **skeuomorphic keycap buttons** and rocker switches, bookings as **ticket stubs** with
  perforations and QR passes, utilisation as an **analog gauge**, and rubber-stamp approvals.

```
backend/
  config/            settings, urls, celery
  apps/
    accounts/        users, roles, departments, JWT
    catalogue/       resources, types, locations, images, seed_demo command
    rules/           availability rules, blackouts, quotas, policy, availability engine
    timetable/       P13 integration
    bookings/        engine, ledger, check-in, no-shows, sweeps, tests
    approvals/       workflows + decisions
    maintenance/  consumables/  analytics/  notifications/
frontend/src/
  pages/             Landing, Login, Explore, ResourcePage, MyBookings, BookingPage, Scan,
                     Approvals, CampusMap, Profile, admin/*
  components/        AppShell (dock), motion (GSAP/Lenis), ui, BookingTicket, reactbits/*
docs/CONFLICT_PREVENTION.md
```

Campus map pins are approximate block positions on the LPU Phagwara campus. Custodians can
correct them per location in the catalogue.
