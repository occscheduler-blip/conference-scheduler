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

## 3. Run API

```bash
uvicorn app.main:app --reload --port 8000
```

#### To view locally visit: http://127.0.0.1:8000/docs#/

The API includes:
- `GET /health`
- `GET /api/events?limit=10`
- `POST /api/events/ingest`
TODO: update this ^