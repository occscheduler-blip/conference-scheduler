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

To view local frontend, visit: http://localhost:3000

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
- `SUPABASE_STUDENTS_TABLE` (optional, default `students`)

## Endpoints

- `GET /health`
- `GET /api/events?limit=10`
- `POST /api/events/upload-students-csv` (multipart upload, field name: `file`)
  - Required CSV columns: `Student Name`, `Student ID`, `Class Level`, `Preferred Email`

`/api/events` reads from the Supabase table in `SUPABASE_EVENTS_TABLE` (default: `events`).
