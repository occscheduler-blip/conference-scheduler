# FastAPI Backend

## 1. Create environment and install dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
./.venv/bin/pip install -r requirements.txt
```

## 2. Configure environment variables

```bash
cp .env.example .env
```

Set `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_DB_URL` in `.env`.
Optionally set:
- `SUPABASE_SYMPOSIUMS_TABLE` (defaults to `symposiums`)
- `SUPABASE_TIMEFRAMES_TABLE` (defaults to `timeframes`)
- `SUPABASE_STUDENTS_TABLE` (defaults to `students`)

## 3. Run API

```bash
uvicorn app.main:app --reload --port 8000
```

# IMPORTANT: For all database functionality testing, use the following UUID as the symposium ID (for now at least):
9e1fd0da-ea43-48f2-85df-5281a495f054

#### To view locally visit: http://127.0.0.1:8000/docs#/

The API includes:
- `GET /health`
- `GET /api/events?limit=10`
- `POST /api/events/ingest`
TODO: update this ^
