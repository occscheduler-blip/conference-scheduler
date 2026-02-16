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

The API includes:
- `GET /health`
- `GET /api/events?limit=10`
- `POST /api/events` (JSON body: `symposium_name`, `rooms`, `timeframes`)
  - Writes one row to `symposiums` and timeframe rows to `timeframes` with the same `symposium_id`
- `POST /api/events/upload-students-csv` (multipart upload, field name: `file`)
  - Required CSV columns: `Student Name`, `Student ID`, `Class Level`, `Preferred Email`
