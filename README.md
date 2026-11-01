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

# 3. Background sweeps (auto-release, reminders, completion)
#    In dev nothing extra is needed: `runserver` starts the sweeper in-process (AUTO_SWEEP=true).
#    The control room's health strip shows when it last ran. Alternatives:
python manage.py run_scheduler       # standalone loop
celery -A config worker -B -l info   # production-style, uses Redis

# 4. Frontend
cd ../frontend
npm install
npm run dev                          # http://localhost:5173 (hot reload, slower)
npm run demo                         # optimised production build on :5173 — use this to present
```

### Demo personas (password `campus123`)

The login screen has one-click buttons for each.

| UMS ID | Role | Try this |
|---|---|---|
| `demo.student` | Student · CSE | Has a booking that's live **right now**: open *My bookings* and check in from *Scan* |
| `demo.faculty` | Faculty · CSE | Recurring weekly booking; book on behalf of a class (K22CS-B) |
| `demo.staff` | Staff · ECE | Laboratory asset issuance, equipment maintenance, bookings |
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
| **M10 AI Campus Copilot** | `apps/ai_assistant` | Autonomous ReAct agent powered by Groq LPU with multi-key rotation and 7 database tools (`search_rooms`, `check_room_schedule`, `get_my_bookings`, `book_room`, `cancel_booking`, `report_maintenance`, `get_campus_overview`); interactive UI cards rendered in chat |
| Interactive Campus Map | `frontend/pages/CampusMap` | Interactive Leaflet campus map of LPU blocks with live hourly colored vacancy rings |
| Digital Boarding Pass | `frontend/components/BookingTicket` | Aviation-style ticket pass with dynamic live countdown timer, status pill, and one-tap calendar export |
| Notifications | `apps/notifications` | Pushed live over **Server-Sent Events** (toast + bell the instant it happens) and emailed; SMTP via env vars |
| People & master data | `apps/accounts`, `apps/catalogue` | User directory (search, role/department changes, deactivate, reset password, create accounts); resource types (icon, colour, who may book, check-in), locations with click-to-place map pins, departments + heads |
| System health | `/api/system/health` | Control-room strip: database, sweeper heartbeat, live notifications, email mode, Redis |
| Calendar sync | `/api/calendar/<token>.ics` | Personal iCal feed for Google / Outlook / Apple; per-booking `.ics` |
| Navigation Redirect | `config/urls.py` | Visiting `http://127.0.0.1:8000/` automatically redirects to the frontend SPA at `http://localhost:5173/` |

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
| AI Copilot ReAct tool calling & key failover | `apps/ai_assistant/tests.py` (Groq API pool, 7 tool dispatches, card schemas) |

```bash
# Run full automated test suite (228 tests passing across all 11 apps)
cd backend && python manage.py test apps

# Verified test breakdown:
python manage.py test apps.bookings      # 50 tests: engine, 500-way concurrency race, full HTTP API
python manage.py test apps.analytics     # 48 tests: heatmaps, snapshots, idle capacity, utilisation
python manage.py test apps.rules         # 24 tests: availability rules, blackouts, policy engine, quotas
python manage.py test apps.approvals     # 16 tests: multi-tier workflow transitions, review queue
python manage.py test apps.notifications # 16 tests: SSE event streaming, email notifications
python manage.py test apps.catalogue     # 14 tests: faceted search, bulk CSV import, QR posters
python manage.py test apps.consumables   # 14 tests: atomic stock decrement, issuances, restock
python manage.py test apps.accounts      # 12 tests: JWT auth, directory CRUD, role permissions
python manage.py test apps.timetable     # 12 tests: timetable publishing, webhook sync, displacement
python manage.py test apps.maintenance   # 12 tests: windows, breakdown reports, downtime tracking
python manage.py test apps.ai_assistant  # 10 tests: agent loop, multi-key rotation, 7 ReAct tools
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
POST /api/ai/chat                        GET  /api/ai/suggestions            (Campus Copilot)
GET  /api/notifications/stream          (Live SSE event stream)
```

---

## Stack & design

* **Backend:** Django 5.2, DRF, SimpleJWT, PostgreSQL 16 range types + `btree_gist`, Celery Beat on
  Redis (sweeps only), Groq API Python SDK (OpenAI tool calling with LPU inference), `qrcode`, `ics`.
* **Frontend:** React 19 + Vite + TypeScript, TanStack Query, FullCalendar (drag-to-select),
  GSAP ScrollTrigger + Lenis smooth scrolling, Motion, Leaflet (LPU campus map on OpenStreetMap),
  Recharts, html5-qrcode, and React Bits components (Aurora, Threads, Dock, SpotlightCard,
  GlareHover, ScrollVelocity, Magnet, ClickSpark, Noise and more).
* **AI Copilot:** Autonomous ReAct Agent with multi-key pool rotation (`GROQ_API_KEYS`), fallback
  cascades (`openai/gpt-oss-120b`, `gpt-oss-20b`, `qwen/qwen3.8-27b`), keyboard shortcut <kbd>Ctrl</kbd> + <kbd>K</kbd>,
  and interactive UI card rendering.
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
    maintenance/     maintenance windows, breakdowns, technician queue
    consumables/     accessories & consumables inventory
    analytics/       nightly snapshots, heatmap, utilisation, idle assets
    notifications/   live SSE stream (/api/notifications/stream) + email
    ai_assistant/    Campus Copilot: Groq client rotator, 7 ReAct tools, chat API
frontend/src/
  pages/             Landing, Login, Explore, ResourcePage, MyBookings, BookingPage, Scan,
                     Approvals, CampusMap, Profile, admin/*
  components/        AppShell (dock), motion (GSAP/Lenis), ui, BookingTicket, reactbits/*,
                     ai/CampusCopilot (drawer + rich cards)
docs/CONFLICT_PREVENTION.md
```

### Design system

Glassmorphism + bento with tactile (skeuomorphic) controls and a "campus box office" identity:
split-flap departure board, tear-off tickets, rubber stamps, handwritten margin notes.

* **Six themes, each with light and dark**, from [tweakcn](https://tweakcn.com) presets (`src/styles/themes.css`):
  Solar Dusk, Cosmic Night, Northern Lights, Quantum Rose, Ocean Breeze, Elegant Luxury. Switching
  recolours the UI and repaints the shader backdrop in a single frame.
* **[shadcn/ui](https://ui.shadcn.com)** primitives (`src/components/shadcn`): dialogs, sheets, selects, popovers, menus and
  the `/` command palette. **[React Bits](https://reactbits.dev)**: SplitFlapText, TearTicket, Grainient, PrismaticBurst,
  BlurText, ShinyText, GlareHover, DecryptedText.
* All colour derives from theme tokens (`src/styles/foundation.css`); nothing is hard-coded per page.

### Performance budget (why it feels smooth)

* The app backdrop (React Bits Grainient) is rendered **once** as a still frame — glass panels
  re-blur whenever the pixels behind them change, so an animated backdrop would re-blur every
  panel every frame. Only the landing hero animates (PrismaticBurst, 40% resolution, 30 fps,
  paused off-screen, no blend modes).
* The marquee is a pure CSS animation (compositor thread); hero layers are promoted with
  `will-change`, and nothing that moves carries a filter or a blurred text-shadow.
* Native scrolling inside the app; Lenis smooth scrolling only on the landing page's scroll scenes.
* Persistent layout route: the dock, top bar and backdrop never remount between pages.
* Route chunks are preloaded while the browser is idle, and hovering a resource prefetches its
  details and its first calendar week, so pages open with data already in cache.
* Resource cards are memoised, use CSS entrances and `content-visibility`, and skip per-card
  backdrop blur.

Campus map pins are approximate block positions on the LPU Phagwara campus. Custodians can
correct them per location in the catalogue.
