# Conference Scheduler

This project now includes:
- A Next.js frontend in the repository root
- A FastAPI backend in `backend/`
- Supabase database connectivity from the backend

## Frontend Setup

```bash
npm install
npm run dev
```

Optional frontend env (`.env.local`):

```bash
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Required backend env values in `backend/.env`:
- `SUPABASE_URL`
- `SUPABASE_KEY`

## Endpoints

- `GET /health`
- `GET /api/events?limit=10`

`/api/events` reads from the Supabase table in `SUPABASE_EVENTS_TABLE` (default: `events`).
