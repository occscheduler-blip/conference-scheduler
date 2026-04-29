# Conference Scheduler

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688)](https://fastapi.tiangolo.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E)](https://supabase.com)

> An automated scheduling tool for academic symposiums. Admins configure rooms and time windows; a constraint-programming solver assigns every presentation a room and time slot while respecting professor and student availability.

---

<!-- Replace with a screenshot or GIF of the schedule grid -->
![Schedule grid placeholder](docs/database_diagram.png)

---

## Who is this for?

Jump to the section that fits you:

| I am a… | Go to |
|---------|-------|
| Attendee or end user | [Using the App](#using-the-app) |
| Potential employer or client | [Project Overview](#project-overview) |
| Developer setting up locally | [Developer Setup](#developer-setup) |

---

## Using the App

The live app is hosted at: **https://conference-scheduler-black.vercel.app**

### Roles

| Role | How to log in | What you can do |
|------|--------------|-----------------|
| **Attendee** | Email OTP | Browse the published schedule, save sessions to your itinerary |
| **Student** | Email OTP | View your assigned presentations, set availability |
| **Professor** | Email OTP | Manage your class presentations, set availability |
| **Department Head** | Email OTP | Create classes, manage professors and students |
| **Admin** | Email + password | Full control: symposiums, rooms, scheduling, publishing |

### How scheduling works

1. An admin creates a symposium with rooms and time windows.
2. Department heads and professors add classes, students, and presentations.
3. Everyone sets their availability.
4. The admin runs the scheduler — the solver assigns each presentation a room and time, respecting all constraints.
5. The admin reviews the draft, adjusts if needed, and publishes.

---

## Project Overview

*For potential employers and clients.*

### What it does

Conference Scheduler automates the most tedious part of running an academic symposium: fitting dozens of student presentations into rooms and time slots while respecting professor schedules, student availability, room capacity, and departmental grouping preferences.

The core solver uses **Google OR-Tools CP-SAT** — a constraint-programming optimizer — to find a schedule that maximizes the number of presentations placed while minimizing quality penalties (availability violations, department fragmentation, room imbalance).

### Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python), Uvicorn |
| Database | Supabase (managed PostgreSQL) |
| Optimizer | Google OR-Tools CP-SAT |
| Auth | JWT (HS256), bcrypt, OTP via Resend email |
| Testing | Vitest (frontend), pytest + mypy (backend) |
| Deployment | Vercel (frontend), Render (backend) |

### Key features

- **Constraint-programming scheduler** — hard and soft constraints are configurable per symposium; the solver guarantees no room or person conflicts
- **Role-based access** — five distinct roles with JWT authentication and per-endpoint enforcement
- **Department and class grouping** — the scheduler preferentially clusters presentations by department, then by class
- **Drag-and-drop manual adjustments** — admins can override any solver assignment
- **Export** — publish schedule as `.xlsx` or `.ics` calendar

---

## Developer Setup

*For developers contributing to or deploying this project.*

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Python | 3.11+ | [python.org](https://python.org) or `brew install python` |
| Docker Desktop | latest | [docker.com](https://docker.com) — required for local Supabase |
| Supabase CLI | latest | `brew install supabase/tap/supabase` |

### 1 — Clone and install frontend packages

```bash
git clone https://github.com/mariaioannou/conference-scheduler.git
cd conference-scheduler
npm install
```

The frontend uses Next.js 16, React 19, Tailwind CSS 4, and Vitest. All packages are listed in [`package.json`](package.json).

### 2 — Configure the frontend environment

Create `.env.local` in the repo root:

```bash
cp .env.example .env.local
```

```env
BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=any-secret-you-choose
```

### 3 — Set up the backend Python environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` includes FastAPI, Uvicorn, OR-Tools, Supabase SDK, pytest, mypy, and all other backend dependencies.

### 4 — Start a local database

From the **repo root** (not `backend/`):

```bash
supabase start
```

This pulls Docker images on first run (a few minutes), then starts a local Supabase stack and applies all migrations automatically.

```bash
supabase status   # prints local API URL, SERVICE_ROLE_KEY, DB URL
```

| Service | Local URL |
|---------|-----------|
| Supabase API | http://127.0.0.1:54321 |
| PostgreSQL | postgresql://postgres:postgres@127.0.0.1:54322/postgres |
| Supabase Studio | http://127.0.0.1:54323 |
| Email (Inbucket) | http://127.0.0.1:54324 |

### 5 — Configure the backend environment

```bash
cp backend/.env.example backend/.env
```

Fill in `backend/.env` with the values from `supabase status`:

```env
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=<SERVICE_ROLE_KEY from supabase status>
SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
JWT_SECRET_KEY=any-random-string
RESEND_API_KEY=            # optional — needed to send OTP emails
RESEND_FROM=noreply@example.com
```

Full list of backend environment variables:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_KEY` | Yes | — | Supabase service role key |
| `JWT_SECRET_KEY` | Yes | — | HS256 signing secret |
| `SUPABASE_DB_URL` | Tests only | — | Direct PostgreSQL URL |
| `RESEND_API_KEY` | No | — | Email OTP delivery |
| `RESEND_FROM` | No | `noreply@hamilton.edu` | OTP sender address |
| `BACKEND_CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `JWT_TTL_HOURS` | No | `24` | Token lifetime |
| `APP_ENV` | No | `development` | Environment label |

### 6 — Create the first admin user

```bash
cd backend
python scripts/create_admin.py --email you@example.com
# Prompted for a password
```

### 7 — Run the app

Open two terminals:

```bash
# Terminal 1 — backend (from backend/)
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
# Swagger docs: http://127.0.0.1:8000/docs
```

```bash
# Terminal 2 — frontend (from repo root)
npm run dev
# App: http://localhost:3000
```

---

## Common Commands

```bash
# Frontend
npm run dev          # dev server
npm run build        # production build
npm run lint         # ESLint
npm test             # Vitest unit tests

# Backend (activate .venv first)
uvicorn app.main:app --reload --port 8000

# Tests — run after making changes (backend requires supabase start)
cd backend && make test                          # mypy type check + full pytest suite
.venv/bin/pytest -q tests/test_api.py           # API tests only
.venv/bin/pytest -q -k "test_schedule"          # single test by name
npm test                                        # frontend tests (no backend needed)

# Database
supabase start / stop / status
supabase migration up    # apply new migration files
```

---

## Project Structure

```
conference-scheduler/
├── app/                        # Next.js frontend
│   ├── pages/                  # One file per role/view
│   └── lib/                    # Shared components and hooks
│       ├── ScheduleGrid.tsx    # Drag-and-drop calendar
│       ├── api.ts              # Backend API client
│       └── __tests__/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app, CORS
│   │   ├── config.py           # Env var schema (Pydantic Settings)
│   │   ├── auth/               # JWT, bcrypt, OTP, Resend email
│   │   ├── routers/            # API route handlers (one file per entity)
│   │   ├── scheduler/          # CP-SAT optimizer
│   │   │   ├── models.py       # Pure-Python dataclasses (solver boundary)
│   │   │   ├── cp_sat.py       # OR-Tools CP-SAT solver
│   │   │   └── service.py      # Loads DB data → builds problem → saves result
│   │   └── supabase_io/        # DB layer (read, write, delete, nested_read)
│   ├── scripts/
│   │   └── create_admin.py     # Bootstrap script
│   ├── tests/                  # Integration tests (real local Supabase)
│   ├── requirements.txt
│   └── Makefile                # make test → mypy + pytest
├── supabase/
│   └── migrations/             # 11+ SQL migration files
├── docs/                       # Architecture diagrams and walkthroughs
├── public/                     # Static assets
├── package.json
├── .env.example                # Frontend env template
├── CITATIONS.md
└── LICENSE
```

---

## License

MIT — see [LICENSE](LICENSE) for the full text and third-party attributions.

## Citations

See [CITATIONS.md](CITATIONS.md) for all third-party library and resource citations.
