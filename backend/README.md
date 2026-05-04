# FastAPI Backend

## Setup

### 1. Create environment and install dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_KEY` | Yes | — | Supabase service role key |
| `JWT_SECRET_KEY` | Yes | — | HS256 secret for signing JWT tokens |
| `SUPABASE_DB_URL` | No | — | Direct PostgreSQL URL (used by tests) |
| `APP_NAME` | No | `Conference Scheduler API` | API title shown in docs |
| `APP_ENV` | No | `development` | Environment label |
| `APP_PORT` | No | `8000` | Server port |
| `BACKEND_CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `JWT_TTL_HOURS` | No | `24` | JWT token lifetime in hours |
| `RESEND_API_KEY` | No | — | Resend API key for OTP emails |
| `RESEND_FROM` | No | `noreply@hamilton.edu` | Sender address for OTP emails |

### 3. Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger docs: http://127.0.0.1:8000/docs

### 4. Create the first admin user

The admin login system requires at least one admin in the database. Use the bootstrap script:

```bash
cd backend
python scripts/create_admin.py --email you@hamilton.edu
# You'll be prompted for a password
```

## Local Database Setup

Tests and local development use [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) to run a local PostgreSQL instance in Docker.

### Prerequisites

- **Docker** — must be running
- **Supabase CLI** — install via `brew install supabase/tap/supabase` or see [docs](https://supabase.com/docs/guides/local-development/cli/getting-started)

### Start local Supabase

From the project root (not `backend/`):

```bash
supabase start
```

This spins up local Supabase containers and automatically applies migrations from `supabase/migrations/`. On first run it will pull Docker images, which may take a few minutes.

| Service | Port |
|---------|------|
| Supabase REST API | 54321 |
| PostgreSQL | 54322 |
| Supabase Studio (UI) | 54323 |
| Email testing (Inbucket) | 54324 |

### Get local credentials

After starting, run:

```bash
supabase status
```

This prints the local `API URL`, `SERVICE_ROLE_KEY`, and `DB URL`. Use these in your `backend/.env`:

```env
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=<SERVICE_ROLE_KEY from supabase status>
SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
JWT_SECRET_KEY=any-secret-you-choose
```

### Apply migrations manually (if needed)

Migrations run automatically on `supabase start`, but if you add new migration files:

```bash
supabase migration up
```

### Stop local Supabase

```bash
supabase stop
```

## Testing

Tests require a running local Supabase instance. The test fixtures (`conftest.py`) automatically point at `127.0.0.1:54321` and override any production env vars.

### Run all tests

```bash
cd backend
make test        # Runs mypy (type check) + pytest
```

### Run tests directly

```bash
cd backend
.venv/bin/pytest -q tests              # All tests
.venv/bin/pytest -q tests/test_api.py  # API tests only
.venv/bin/pytest -q tests/test_auth.py # Auth tests only
```

## Authentication

The API uses JWT Bearer tokens for authentication:

- **Admin login:** POST email + password to `/api/auth/admin/login`, receive a JWT Bearer token
- **OTP login:** Department heads, professors, and students receive a one-time code via email
- Write operations (POST, PUT, DELETE) on event routes require a valid JWT Bearer token with the appropriate role
- GET endpoints on event routes are public (no token required)

Include the token in requests:

```http
Authorization: Bearer <token>
```

## API Endpoints

Base URL: `http://127.0.0.1:8000`

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |

### Auth Routes (`/api/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/admin/login` | None | Admin login (email + password) → JWT |
| POST | `/api/auth/admin/create` | JWT (admin) | Create a new admin user |
| POST | `/api/auth/otp/request` | None | Request OTP code (email + role) |
| POST | `/api/auth/otp/verify` | None | Verify OTP → JWT |

### Event Routes (`/api/events`)

GET endpoints are public. Write operations (POST/PUT/DELETE) require a JWT Bearer token with an authorized role.

#### Create (POST)

| Path | JWT Roles | Description |
|------|-----------|-------------|
| `/api/events/add_symposium` | admin | Create symposium + timeframes |
| `/api/events/add_department` | admin | Create department under symposium |
| `/api/events/add_class` | admin, department_head | Create class + professors |
| `/api/events/add_students` | admin, department_head, professor | Bulk insert students into class |
| `/api/events/add_presentation` | admin, department_head, professor | Create presentation + assign students |
| `/api/events/add_request` | admin, department_head, professor, student | Student requests someone attends their lecture |

#### Read (GET)

| Path | Query Params | Description |
|------|-------------|-------------|
| `/api/events/symposiums` | — | All symposiums |
| `/api/events/symposiums/{symposium_id}` | — | Single symposium + timeframes |
| `/api/events/departments` | `symposium_id?`, `include?` | Departments (optional nested data) |
| `/api/events/classes` | `department_id?`, `include?` | Classes (optional nested data) |
| `/api/events/students` | `class_id?` | Students in class |
| `/api/events/presentations` | `class_id?` | Presentations (enriched with presenting students) |
| `/api/events/professors` | `class_id?` | Professors in class |
| `/api/events/timeframes` | `linked_id?` | Timeframes for any entity |
| `/api/events/requests` | `student_id?` | Professor requests from student |

The `include` parameter (on `/departments` and `/classes`) accepts a comma-separated list:
`?include=classes,professors,students,presentations,timeframes`

#### Update (PUT)

| Path | JWT Roles | Description |
|------|-----------|-------------|
| `/api/events/update_symposium` | admin | Update symposium fields + replace timeframes |
| `/api/events/update_department` | admin, department_head | Update department fields |
| `/api/events/update_class` | admin, department_head, professor | Update class fields |
| `/api/events/update_professor` | admin, department_head, professor | Update professor fields |
| `/api/events/update_student` | admin, department_head, professor, student | Update student fields |
| `/api/events/update_presentation` | admin, department_head, professor, student | Update presentation + reassign students |
| `/api/events/update_timeframes` | admin, department_head, professor, student | Replace all timeframes for a linked entity |

#### Delete (DELETE)

| Path | JWT Roles | Cascades To |
|------|-----------|-------------|
| `/api/events/delete_symposium?symposium_id=` | admin | departments → classes → all children |
| `/api/events/delete_department?department_id=` | admin | classes → all children |
| `/api/events/delete_class?class_id=` | admin, department_head | students, professors, presentations + children |
| `/api/events/delete_student?student_id=` | admin, department_head, professor | presenting_students, requests, timeframes |
| `/api/events/delete_professor?professor_id=` | admin, department_head | timeframes |
| `/api/events/delete_presentation?presentation_id=` | admin, department_head, professor | presenting_students, timeframes |

## Project Structure

```
backend/
├── app/
│   ├── main.py               # FastAPI app, CORS, health check
│   ├── config.py             # Pydantic Settings (env vars)
│   ├── security.py           # API key dependency
│   ├── utils.py              # force_uuid helper
│   ├── auth/
│   │   ├── password.py       # hash_password / verify_password (bcrypt)
│   │   ├── jwt_utils.py      # encode_jwt / decode_jwt, JWTClaims
│   │   ├── dependencies.py   # require_jwt() dependency factory
│   │   ├── otp.py            # OTP generation and verification
│   │   └── email.py          # OTP email sending (Resend)
│   ├── routers/
│   │   ├── events.py         # All event API route handlers
│   │   ├── auth.py           # Admin login/create + OTP endpoints
│   │   └── request_schemas.py # Pydantic request models
│   └── supabase_io/
│       ├── client.py         # Supabase client instance
│       ├── read.py           # GET queries
│       ├── write.py          # INSERT/UPDATE
│       ├── delete.py         # Cascade delete logic
│       ├── nested_read.py    # ?include= nested fetching
│       └── supabase_schemas.py # DB record Pydantic models
├── scripts/
│   └── create_admin.py       # CLI: bootstrap first admin user
├── tests/
│   ├── conftest.py           # Fixtures, local Supabase setup
│   ├── db_helper.py          # Direct psycopg connection for tests
│   ├── test_api.py           # ~40 integration tests
│   └── test_auth.py          # 8 JWT auth integration tests
├── requirements.txt
├── Makefile                  # `make test` → mypy + pytest
├── pytest.ini
└── mypy.ini                  # Strict mode
```

## Citations

Project-wide citations are listed in [../CITATIONS.md](../CITATIONS.md).
