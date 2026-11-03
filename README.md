# BookMyCampus

Campus resource, lab and facility booking platform for Lovely Professional University, built with Django, PostgreSQL and React.

**Live demo:** https://book-my-campus-ab.vercel.app

The demo runs on free hosting, so the first load after a quiet period can take up to a minute.

![BookMyCampus landing page](docs/screenshots/landing.jpg)

## About

This is our project for problem statement **P20: Campus Resource, Lab and Facility Booking Platform** (Track P).

At the moment, booking a lab or hall on campus usually means asking around on WhatsApp, writing in a register or calling someone in the department. BookMyCampus puts all of it in one place. You can see what is free, book it, get a QR pass and check in at the door. If nobody checks in, the slot is released for other people.

The demo has 32 resources across 7 types: classrooms, laboratories, equipment, seminar halls, sports facilities, meeting rooms and vehicles. All the data in it is sample data, and this is a student project, not an official LPU system.

## Features

**Students and faculty**

- Search and filter resources by type, block and capacity, or show only what is free this hour
- Room calendar that already shows classes from the timetable, maintenance and other bookings
- Book for yourself or for a class. A student's class booking always needs HOD approval
- QR pass for each booking, with check-in by scanning the poster on the room door
- Waitlist for a taken slot, with a notification if it opens up
- Similar rooms that are free at the same time as a taken slot
- Hourly chart on each room showing when it is usually quiet
- Saved rooms, a personal calendar and calendar export (`.ics` file or iCal feed)
- Campus map showing how much of each block is free
- Faculty can also repeat a booking weekly, and book seminar halls and vehicles

**HOD**

- Approval queue for requests from their department and for rooms their department owns
- Add and edit rooms, including CSV import
- Usage analytics: utilisation, idle assets, a weekday-by-hour heatmap, no-shows and demand

**Campus rules and operations**

- Opening hours, booking length limits, notice period, blackout dates and weekly quotas
- Approval workflows set per resource type and role, editable without redeploying
- Check-in window with a 15-minute grace period, then automatic release
- No-show strikes: a warning, then a 7-day pause, then a 30-day pause
- Timetable sync through a webhook or a URL. Bookings that clash after an update are moved off and notified
- Maintenance windows and breakdown reports
- Consumable stock that can be issued with a booking
- Live notifications using Server-Sent Events, plus email if SMTP is set up

**Campus Copilot (AI assistant)**

Press <kbd>Ctrl</kbd> + <kbd>K</kbd> and ask in normal language. It reads live data and can search rooms, check schedules, book, cancel or report a fault. It uses the Groq API with tool calling.

## Screenshots

| Sign up | Sign in |
|---|---|
| ![Sign up](docs/screenshots/register.jpg) | ![Sign in](docs/screenshots/login.jpg) |

| Explore | Room calendar |
|---|---|
| ![Explore](docs/screenshots/explore.jpg) | ![Room calendar](docs/screenshots/calendar.jpg) |

| Booking form | Taken slot |
|---|---|
| ![Booking form](docs/screenshots/booking-drawer.jpg) | ![Taken slot](docs/screenshots/taken.jpg) |

| Booking pass | My bookings |
|---|---|
| ![Booking pass](docs/screenshots/pass.jpg) | ![My bookings](docs/screenshots/bookings.jpg) |

| My calendar | Campus map |
|---|---|
| ![My calendar](docs/screenshots/my-calendar.jpg) | ![Campus map](docs/screenshots/map.jpg) |

| Campus Copilot | Copilot answering |
|---|---|
| ![Campus Copilot](docs/screenshots/copilot-welcome.jpg) | ![Copilot answering](docs/screenshots/copilot.jpg) |

| HOD approvals | Analytics |
|---|---|
| ![HOD approvals](docs/screenshots/approvals.jpg) | ![Analytics](docs/screenshots/analytics.jpg) |

| Catalogue | Profile |
|---|---|
| ![Catalogue](docs/screenshots/catalogue.jpg) | ![Profile](docs/screenshots/profile.jpg) |

There are six colour themes, each with a light and dark mode:

| Cosmic Night | Northern Lights | Quantum Rose |
|---|---|---|
| ![Cosmic Night](docs/screenshots/theme-cosmic.jpg) | ![Northern Lights](docs/screenshots/theme-northern.jpg) | ![Quantum Rose](docs/screenshots/theme-rose.jpg) |

It also works on phones:

| Explore | Pass | Copilot |
|---|---|---|
| ![Explore on a phone](docs/screenshots/phone-explore.jpg) | ![Pass on a phone](docs/screenshots/phone-pass.jpg) | ![Copilot on a phone](docs/screenshots/phone-copilot.jpg) |

## Demo accounts

The login page has one-click buttons for these accounts. If you want to type them in, the password is `campus123`.

| Username | Role |
|---|---|
| `demo.student` | Student (CSE) |
| `demo.faculty` | Faculty (CSE) |
| `demo.head` | HOD (CSE) |

New students can also register at `/register` with their 8-digit registration number. Sign-up always creates a Student account.

To see the main flow:

1. Sign in as Student, open a room and click a free slot.
2. Choose **For a class**, enter a class such as `K22CS-B` and send the request.
3. Sign in as HOD, open **Approvals** and approve it.
4. Sign in as Student again. The booking is now confirmed, with a QR pass.

## Tech stack

| Part | Used |
|---|---|
| Backend | Django 5.2, Django REST Framework, SimpleJWT |
| Database | PostgreSQL 16 |
| Background jobs | Sweeper loop (`run_scheduler`), or Celery with Redis |
| Frontend | React 19, TypeScript, Vite, TanStack Query |
| UI | Tailwind CSS, shadcn/ui, React Bits, GSAP, FullCalendar, Leaflet, Recharts |
| AI | Groq API |
| Hosting | Vercel (frontend), Render (backend and database) |

## Running it locally

You need Python 3.12+, Node 20+ and Docker Desktop.

Start PostgreSQL and Redis:

```bash
docker compose up -d
```

Start the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo --reset
python manage.py runserver 127.0.0.1:8000
```

`seed_demo --reset` deletes all existing users and bookings, so only run it when setting up.

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. Use `npm run demo` instead of `npm run dev` for a faster production build.

Campus Copilot needs a Groq API key. Add it to `backend/.env` as `GROQ_API_KEYS`. The other settings are listed in `backend/.env.example`.

## How double booking is prevented

Checking that a slot is free and then saving the booking is not safe, because two requests can pass the check at the same time. So each booking stores its time as a PostgreSQL range, and the table has an exclusion constraint:

```python
ExclusionConstraint(
    name="booking_no_overlap",
    expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
    condition=Q(status__in=["pending", "confirmed", "checked_in"]),
)
```

The database itself refuses the second booking, and the API returns a `409` with the reason. A second constraint applies the same rule across bookings, timetabled classes and maintenance.

`test_concurrency.py` sends 500 simultaneous attempts at one slot, each on its own database connection, and checks that exactly one booking exists afterwards. More detail is in [docs/CONFLICT_PREVENTION.md](docs/CONFLICT_PREVENTION.md).

## Testing

```bash
cd backend
python manage.py test
```

There are 266 backend tests. PostgreSQL has to be running, and a full run takes several minutes.

| Requirement | Where it is checked |
|---|---|
| 500 concurrent attempts give exactly one booking | `apps/bookings/tests/test_concurrency.py` |
| Timetabled slots are never offered | `test_timetabled_slot_never_offered`, `test_cannot_book_over_lecture` |
| Workflows can change per type without a deployment | Control room, Rules & workflows |
| Mobile QR check-in and auto-release after the grace period | `/scan` page, `CheckInAndReleaseTest` |
| No-show tracking with progressive restriction | `test_progressive_restriction` |
| Utilisation and idle capacity across 3 or more types | Control room, Analytics |
| Recurring bookings with per-date conflict handling | `RecurringTest` |

## Project structure

```text
backend/
  config/            settings and URLs
  apps/
    accounts/        users, roles, departments, sign-up
    catalogue/       resources, types, locations, demo data
    rules/           availability, blackouts, quotas
    bookings/        booking engine, check-in, no-shows, waitlist
    approvals/       workflows and decisions
    timetable/       timetable sync
    maintenance/     maintenance windows and breakdown reports
    consumables/     stock and issuing
    analytics/       usage reports
    notifications/   live notifications and email
    ai_assistant/    Campus Copilot
frontend/src/
  pages/             one file per page
  components/        shared components
  styles/            themes and stylesheets
docs/                design notes and screenshots
```

## Deployment

The backend and database are on Render, using `render.yaml`. In Render, choose **New → Blueprint** and select this repo. It creates both, runs the migrations and loads the sample data. Then set `FRONTEND_URL` and `CORS_ALLOWED_ORIGINS` to the Vercel address.

The frontend is on Vercel, with `frontend` as the root directory. `frontend/vercel.json` forwards `/api` requests to the Render backend, so update it if your Render address is different.

## Known limitations

- Registration numbers are not verified, because there is no connection to LPU's UMS. Someone could register with another student's number.
- There is no self-service password reset. An administrator can reset a password from the People page.
- Sign-in attempts are not rate limited yet.
- Any signed-in user can block a room for 24 hours with a breakdown report. A real deployment should have staff confirm reports first.
- Scanning QR codes with a phone camera needs HTTPS, except on `localhost`.
- Campus map pins are approximate.
- On the free hosting, uploaded images are lost on each redeploy and the database expires after about 30 days.

## Team

- [Ankit Basu](https://github.com/Ankit-Basu)
- [Ankan Basu](https://github.com/ankan123basu)

Room photos are from [Unsplash](https://unsplash.com) and map data is from [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
