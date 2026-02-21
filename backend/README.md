# FastAPI Backend

## Setup

### 1. Create environment and install dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
./.venv/bin/pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Set these in `.env`:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_DB_URL`
- `BACKEND_API_KEY`

Optional:
- `SUPABASE_EVENTS_TABLE` (default: `events`)
- `SUPABASE_SYMPOSIUMS_TABLE` (default: `symposiums`)
- `SUPABASE_TIMEFRAMES_TABLE` (default: `timeframes`)
- `SUPABASE_STUDENTS_TABLE` (default: `students`)

### 3. Run API

```bash
uvicorn app.main:app --reload --port 8000
```

Open docs at `http://127.0.0.1:8000/docs`.

For protected endpoints under `/api/events/*`, include the header:

```http
X-API-Key: <your BACKEND_API_KEY value>
```

## Testing

Tests live in `backend/tests`.

Run all tests:

```bash
cd backend
make test
```

Equivalent direct command:

```bash
cd backend
.venv/bin/pytest -q tests
```

Run one test file:

```bash
cd backend
.venv/bin/pytest -q tests/test_events_api.py
```

## API Endpoints (Current)

Base URL: `http://127.0.0.1:8000`

### Health
- `GET /health`

### Events
- `POST /api/events/add_symposium`
- `POST /api/events/add_department`
- `POST /api/events/add_class`
- `POST /api/events/add_students`
- `POST /api/events/add_presentation`
- `POST /api/events/add_prof_req`
- `PUT /api/events/update_timeframes`
- `GET /api/events/get_symposiums`
- `GET /api/events/get_departments`
- `GET /api/events/get_classes`
- `GET /api/events/get_students`
- `GET /api/events/get_presentations`
- `GET /api/events/get_professors`
- `GET /api/events/get_timeframes`
- `GET /api/events/get_prof_requests`
- `DELETE /api/events/delete_symposium`
