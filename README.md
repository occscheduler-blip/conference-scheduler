# Conference Scheduler

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688)](https://fastapi.tiangolo.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E)](https://supabase.com)

> An automated scheduling tool for the Hamilton College Oral Communication Center thesis symposia. Admins configure rooms and time windows; a constraint-programming solver assigns every presentation a room and time slot while respecting professor and student availability.

---

![Schedule grid](schedule-screenshot.jpeg)

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
| **Admin** | Email + password | Full control: symposia, rooms, scheduling, publishing |
| **Super Admin** | Email + password | Everything an admin can do, plus create/edit/delete other admins and reset their passwords |

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

For symposia with more than ~100 presentations or ~15 classes, a **hierarchical scheduler** kicks in automatically: it bundles each class into a single block, places the blocks with a small CP-SAT model, then expands each block into its individual presentations and runs an identity-keyed verification sweep so the same person entered into multiple classes (a double-major student or cross-listed professor) is still treated as one body. This keeps a 300+ presentation symposium tractable in seconds rather than minutes.

Every constraint is configurable per run as **hard / soft / off** (room conflicts, person conflicts, professor availability, student availability, same-class-same-room, makespan, department span, class span, professor span, room balance). When the solver can't place every presentation, an opt-in **debug mode** runs every combination of hard-constraint relaxations in parallel and tells the admin which switch to flip to schedule the most presentations.

### Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python), Uvicorn |
| Database | Supabase (managed PostgreSQL) |
| Optimizer | Google OR-Tools CP-SAT |
| Auth | JWT (HS256), bcrypt, OTP via Gmail SMTP |
| Testing | Vitest (frontend), pytest + mypy (backend) |
| Deployment | Vercel (frontend), Oracle Cloud Always Free VM + Caddy + systemd (backend) |

### Key features

- **Two-tier constraint-programming scheduler** — a flat CP-SAT model for small/medium symposia and a hierarchical class-block solver that takes over above ~100 presentations or ~15 classes; the dispatch is automatic
- **Configurable constraint modes** — every hard/soft/off setting (room, person, professor and student availability, same-class-same-room, makespan, department/class/professor span, room balance) is tunable per run
- **Debug mode** — when a run leaves presentations unscheduled, opt in to an exhaustive parallel probe that tells the admin which constraint relaxation would schedule the most presentations
- **Identity-keyed person tracking** — double-major students and cross-listed faculty are deduplicated by email so they can never be double-booked, even across classes
- **Role-based access** — six roles (attendee, student, professor, department head, admin, super admin) with JWT authentication and per-endpoint enforcement; only super admins can manage other admins
- **Drag-and-drop manual adjustments** — admins can drag presentations on a calendar grid; conflicts surface a confirmation dialog letting an admin override and place the presentation anyway
- **Adaptive grid** — the schedule editor's grid auto-fits the symposium's actual time windows and presentation durations rather than a hardcoded 9 AM / 15-minute lattice
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
SMTP_HOST=smtp.gmail.com   # optional in local dev — without it, OTPs are logged instead of sent
SMTP_PORT=587
SMTP_USERNAME=your.email@hamilton.edu
SMTP_PASSWORD=xxxxxxxxxxxxxxxx     # 16-char Google App Password (requires 2-Step Verification)
SMTP_FROM=Conference Scheduler <your.email@hamilton.edu>
```

Full list of backend environment variables:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_KEY` | Yes | — | Supabase service role key |
| `JWT_SECRET_KEY` | Yes | — | HS256 signing secret |
| `SUPABASE_DB_URL` | Tests only | — | Direct PostgreSQL URL (used by `tests/db_helper.py`) |
| `SMTP_HOST` | No | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | No | `587` | SMTP STARTTLS port |
| `SMTP_USERNAME` | No | — | Sending mailbox address. If unset, OTPs are logged at WARNING instead of sent |
| `SMTP_PASSWORD` | No | — | Mailbox app password (Gmail: 16-char App Password) |
| `SMTP_FROM` | No | `SMTP_USERNAME` | `Name <addr@example.com>` format; defaults to `SMTP_USERNAME` |
| `BACKEND_CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `SITE_URL` | No | first CORS origin | Public frontend URL embedded in OTP emails |
| `JWT_TTL_HOURS` | No | `24` | Token lifetime |
| `APP_NAME` | No | `Conference Scheduler API` | Title shown in Swagger |
| `APP_ENV` | No | `development` | Environment label |
| `APP_PORT` | No | `8000` | Server port (uvicorn `--port` overrides) |

### 6 — Create the first admin user

```bash
cd backend
# Plain admin (cannot manage other admins)
python scripts/create_admin.py --email you@example.com

# Super admin — bootstrap account that can create/edit/delete other admins
python scripts/create_superadmin.py --email you@example.com

# Promote an existing admin to super admin
python scripts/create_superadmin.py --email existing@hamilton.edu --promote-existing
```

Both scripts prompt for a password if `--password` isn't supplied.

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

## Production Backend Deployment

The production backend runs on an Oracle Cloud "Always Free" VM with Caddy as a TLS-terminating reverse proxy and systemd supervising uvicorn. Gmail SMTP is used for OTP and notification emails — the sender mailbox is a Hamilton Google Workspace address, so DKIM/SPF authenticate as `hamilton.edu` and mail lands in the inbox.

```
Internet → Caddy (443/TLS, Let's Encrypt) → uvicorn (127.0.0.1:8000) → FastAPI
```

| Layer | Detail |
|-------|--------|
| Host | Oracle Cloud Always Free, `VM.Standard.E2.1.Micro` (AMD, 1/8 OCPU + 1 GB RAM), Ubuntu 24.04, `us-ashburn-1` |
| Public DNS | `occscheduler.duckdns.org` — DuckDNS A record pointing at the VM's public IPv4 |
| TLS | Caddy auto-provisions and renews a Let's Encrypt cert on first start |
| Process supervision | `systemd` unit `conference-scheduler` (`Restart=on-failure`, starts on boot) |
| Python | 3.14 via `uv`-managed install; venv at `/home/ubuntu/conference-scheduler/backend/.venv` |
| Swap | 2 GB swap file at `/swapfile` — the 1 GB-RAM micro relies on it for OR-Tools spikes |
| Outbound SMTP | Gmail SMTP on port 587. Reason for not running on Render: Render's free tier blocks outbound SMTP; OCI allows it |
| Solver wall-clock cap | 3600s (set in `backend/app/scheduler/service.py:build_schedule_for_symposium`). The throttled micro takes ~110s for a 200-presentation symposium; expect a faster shape (Ampere A1 ARM when capacity allows) to drop this to under 30s |

### Routine update — pushing new code

After merging changes to `main`:

```bash
# From your laptop
git push origin main

# Then on the VM
ssh occs-vm
cd ~/conference-scheduler && git pull
# Only if backend/requirements.txt changed:
#   source backend/.venv/bin/activate && uv pip install -r backend/requirements.txt
sudo systemctl restart conference-scheduler
sudo journalctl -u conference-scheduler -n 30 --no-pager   # sanity-check the restart
```

The frontend deploys itself on every `main` push via Vercel — nothing to do there.

### Applying a Supabase migration to production

Local `supabase start` re-applies every migration in `supabase/migrations/` automatically. The hosted Supabase project does **not** — new migrations have to be applied by hand. The safe path:

1. Open the **Supabase dashboard → SQL editor** for the project referenced by `SUPABASE_URL`.
2. Paste the SQL from the new migration file (`supabase/migrations/<timestamp>_<name>.sql`) and run it.
3. Confirm by running a quick `SELECT` that exercises the change, or just retry the action that needed it.

The migration files are intentionally small and idempotent (each starts with `DROP CONSTRAINT IF EXISTS` etc.), so running one twice is safe.

### Changing the production `.env`

`backend/.env` lives only on the VM (it holds the Supabase service-role key, JWT secret, and Gmail App Password — none of which belong in git). To edit:

```bash
ssh occs-vm
nano ~/conference-scheduler/backend/.env
sudo systemctl restart conference-scheduler
```

If you ever lose the file, copy your laptop's working copy back over:

```bash
# On your laptop
scp ~/Desktop/conference-scheduler/backend/.env occs-vm:~/conference-scheduler/backend/.env
ssh occs-vm 'chmod 600 ~/conference-scheduler/backend/.env && sudo systemctl restart conference-scheduler'
```

### Diagnostics

```bash
# Live log tail (Ctrl+C to exit)
sudo journalctl -u conference-scheduler -f

# Last 200 lines, no paging
sudo journalctl -u conference-scheduler -n 200 --no-pager

# Just schedule-timing lines
sudo journalctl -u conference-scheduler | grep -E "place_blocks|hierarchical complete|build_schedule_for_symposium total wall"

# OOM kills (memory hypothesis check)
sudo journalctl -k --since "1 hour ago" | grep -i -E 'oom|killed|out of memory'

# Live memory + CPU
watch -n 1 free -h
```

### Where things live on the VM

| Path | Contents |
|------|----------|
| `~/conference-scheduler` | Git checkout (`origin/main`) |
| `~/conference-scheduler/backend/.venv` | Python 3.14 venv (uv-managed) |
| `~/conference-scheduler/backend/.env` | Runtime secrets, `chmod 600`, NOT in git |
| `/etc/systemd/system/conference-scheduler.service` | systemd unit |
| `/etc/caddy/Caddyfile` | Reverse proxy + TLS config |
| `/etc/iptables/rules.v4` | Persistent firewall rules (22, 80, 443 allowed) |
| `/swapfile` | 2 GB swap |

### Updating Caddy (TLS / domain) config

```bash
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -f   # watch cert renewal / proxy errors
```

The current Caddyfile is essentially:

```
occscheduler.duckdns.org {
    reverse_proxy 127.0.0.1:8000
}
```

### If the VM is lost — building a new one from scratch

The free-tier VM could theoretically be reclaimed (idle for 7+ days, account inactivity, capacity change). Rebuild path:

1. **Provision** an Ubuntu 24.04 instance in Oracle Cloud Always Free. Ampere A1 ARM (`VM.Standard.A1.Flex`, 2 OCPU / 12 GB) is preferred if `us-ashburn-1` has capacity; otherwise the AMD `VM.Standard.E2.1.Micro` works. Assign a public IPv4 and paste the `id_ed25519_occscheduler.pub` key.
2. **Open ports 80 + 443** in two places — the OCI VCN's Default Security List (Ingress Rules for TCP/80 and TCP/443 from `0.0.0.0/0`), and host iptables (`sudo iptables -I INPUT 5 -m state --state NEW -p tcp --dport 80 -j ACCEPT`, same for 443, then `sudo apt install -y iptables-persistent && sudo netfilter-persistent save`).
3. **System prep**: 2 GB swap (`sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab`), `sudo apt update && sudo apt -y upgrade`, install `git build-essential curl ca-certificates`, then install uv (`curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env`).
4. **Python + repo**: `uv python install 3.14`, `cd ~ && git clone https://github.com/occscheduler-blip/conference-scheduler.git`, `cd ~/conference-scheduler/backend && uv venv --python 3.14 .venv && source .venv/bin/activate && uv pip install -r requirements.txt`.
5. **`.env`**: `scp` from your laptop, `chmod 600`. Verify `APP_ENV=production`, that `SUPABASE_DB_URL` references the current Supabase project, and that the SMTP App Password is current.
6. **systemd**: write `/etc/systemd/system/conference-scheduler.service` running `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` as user `ubuntu`. `sudo systemctl daemon-reload && sudo systemctl enable --now conference-scheduler`.
7. **DuckDNS**: update the `occscheduler` record to point at the new VM's public IPv4.
8. **Caddy**: install from the Cloudsmith repo (per [Caddy's install docs](https://caddyserver.com/docs/install#debian-ubuntu-raspbian)), write the Caddyfile shown above, `sudo systemctl reload caddy`. The Let's Encrypt cert issues in 5–15s; tail `journalctl -u caddy -f` to confirm.
9. **Vercel**: only if the backend domain changed — update the `BACKEND_URL` env var in the Vercel project and redeploy.

The full play-by-play (with the gotchas we hit the first time: iptables rule ordering vs. REJECT, the AMD vs ARM shape, the OCI shape picker hiding the resource sliders behind a ▶, etc.) is in the git history of `README.md` if needed.

---

## Building the Desktop App

*For shipping a self-contained `.dmg` to a non-technical user — bundles the frontend + a local FastAPI backend connected to remote Supabase, so the user doesn't install Docker, Python, or Node.*

The bundled app is currently **macOS Apple Silicon only** (`aarch64`). Intel Macs and Windows would need separate build hosts.

### Additional prerequisites

On top of the dev setup above:

| Tool | Install |
|------|---------|
| Rust toolchain | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Xcode Command Line Tools | `xcode-select --install` |
| PyInstaller (in backend venv) | `cd backend && .venv/bin/pip install pyinstaller` |

### Build

```bash
npm run desktop:build
```

This runs three stages: PyInstaller bundles the FastAPI backend (uses the values in `backend/.env`), Next.js produces a static export with the desktop backend URL baked in, and `tauri build` compiles the Rust shell and packages everything into a `.dmg`.

Output:

```
src-tauri/target/release/bundle/dmg/Conference Scheduler_0.1.0_aarch64.dmg
```

### How it runs

The user double-clicks the app, which:

1. Spawns the bundled FastAPI backend on `127.0.0.1:17850`
2. Shows a splash screen while the backend boots (~3s)
3. Loads the static frontend, which talks to the local backend
4. The local backend talks to **remote Supabase** using the keys from `backend/.env` baked into the bundle

Backend logs land at `~/Library/Logs/Conference Scheduler/backend.log` — first place to look if anything misbehaves.

### Things to know before distributing

- **Unsigned**: the first launch triggers Gatekeeper. The user must **right-click the app → Open** the first time, then approve the warning. Subsequent launches open normally. To remove the warning entirely, sign and notarize with an Apple Developer cert.
- **Embedded credentials**: `backend/.env` (Supabase service-role key, JWT secret) gets baked into the bundle. Anyone with the `.dmg` can extract them. For wider distribution, point the bundle at a separate "test" Supabase project rather than production.
- **Bundle size**: ~104 MB `.dmg` (~270 MB installed). OR-Tools is the largest contributor.

### Iterating

```bash
npm run desktop:dev      # rebuilds backend, runs `tauri dev` with hot frontend reload
```

Frontend code changes hot-reload. Backend or Rust shell changes require re-running the command.

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

# Desktop app (macOS, see "Building the Desktop App" above)
npm run desktop:dev      # dev iteration with hot reload
npm run desktop:build    # produce .app + .dmg in src-tauri/target/release/bundle/
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
│   │   ├── main.py             # FastAPI app, CORS, request logging, health + diagnostics
│   │   ├── config.py           # Env var schema (Pydantic Settings)
│   │   ├── request_context.py  # Per-request id middleware + log filter
│   │   ├── utils.py            # force_uuid helper
│   │   ├── auth/               # JWT, bcrypt, OTP, SMTP email
│   │   │   ├── password.py      # hash_password / verify_password (bcrypt)
│   │   │   ├── jwt_utils.py     # encode_jwt / decode_jwt, JWTClaims
│   │   │   ├── dependencies.py  # require_jwt() FastAPI dependency factory
│   │   │   ├── otp.py           # OTP generation + verification
│   │   │   └── email.py         # OTP email delivery via smtplib (default: Gmail SMTP)
│   │   ├── routers/            # API route handlers, split by entity
│   │   │   ├── events.py            # Aggregator: imports + mounts the per-entity routers below
│   │   │   ├── events_symposiums.py # /add_symposium, /update_symposium, /delete_symposium, /symposiums
│   │   │   ├── events_departments.py# /add_department, /update_department, /delete_department, /departments
│   │   │   ├── events_classes.py    # /add_class, /update_class, /delete_class, /classes
│   │   │   ├── events_people.py     # students + professors + requests CRUD
│   │   │   ├── events_presentations.py # presentation CRUD + buffers
│   │   │   ├── events_timeframes.py # /update_timeframes, /timeframes
│   │   │   ├── events_scheduler.py  # /schedule, /schedule/apply-debug, /schedule_job/{id},
│   │   │   │                        # /publish_schedule, /update_schedule_assignment,
│   │   │   │                        # /bulk_update_schedule_assignments, /temporary_timeframes
│   │   │   ├── events_emails.py     # /email_symposium, /email_classes, /email_students
│   │   │   ├── events_helpers.py    # Shared validators / helpers used across the event routers
│   │   │   ├── auth.py              # Admin login + admin mgmt + OTP + attendee register/itinerary
│   │   │   └── request_schemas.py   # Pydantic request models
│   │   ├── scheduler/          # CP-SAT optimizer
│   │   │   ├── models.py        # Pure-Python dataclasses + ScheduleConstraints
│   │   │   ├── cp_sat.py        # Flat OR-Tools CP-SAT solver (small/medium symposia)
│   │   │   ├── cp_sat_helpers.py # Window utilities + parallel exhaustive debug probe
│   │   │   ├── hierarchical.py  # Class-block decomposition solver (300+ presentations)
│   │   │   ├── conflicts.py     # Conflict detection used by manual schedule edits
│   │   │   └── service.py       # Loads DB data → builds problem → dispatches solver → saves result
│   │   └── supabase_io/         # DB layer (read, write, delete, nested_read, locks)
│   ├── scripts/
│   │   ├── create_admin.py                   # Bootstrap script (plain admin)
│   │   ├── create_superadmin.py              # Bootstrap script (super admin / promote existing)
│   │   ├── repair_out_of_window_assignments.py # One-off cleanup for stale assignments
│   │   ├── seed_symposium.py                 # Generic seeder
│   │   ├── seed_{debug,small,medium,large,large_failing,massive,uniform}_symposium.py # Demo data
│   │   └── seed_all_symposia.py              # Wipe + reseed every demo symposium
│   ├── tests/                  # Integration tests (real local Supabase) + builders.py + TESTS.md
│   ├── desktop_main.py         # PyInstaller entry point for the bundled backend
│   ├── desktop.spec            # PyInstaller spec
│   ├── requirements.txt
│   └── Makefile                # make test → mypy + pytest
├── supabase/
│   └── migrations/             # 11+ SQL migration files
├── src-tauri/                  # Tauri desktop shell (Rust)
│   ├── src/main.rs             # Spawns the Python sidecar, manages lifecycle
│   ├── tauri.conf.json         # Bundle config, window settings
│   └── icons/
├── scripts/                    # Desktop build helpers
│   ├── build-desktop-frontend.mjs  # Static-export wrapper
│   └── copy-sidecar.mjs            # Copies PyInstaller output to src-tauri/binaries/
├── public/                     # Static assets (incl. desktop loader splash)
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
