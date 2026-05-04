# Admin Authentication

## Overview

The app uses JWT Bearer tokens for route protection:

| System | Used for | How |
|--------|----------|-----|
| JWT Bearer token | `/api/auth/*` and `/api/events/*` routes | Login/session endpoints issue JWTs with role claims |

The previous static key route protection has been removed.

---

## How a Login Works (Step by Step)

```
Client                          FastAPI                        Supabase (admins table)
  |                                |                                |
  |-- POST /api/auth/admin/login ->|                                |
  |   { email, password }          |                                |
  |                                |-- SELECT * WHERE email=... --->|
  |                                |<-- row { id, password_hash }---|
  |                                |                                |
  |                                | bcrypt.checkpw(password, hash) |
  |                                |                                |
  |                                | encode_jwt(id, email, "admin") |
  |                                |   signs HS256 with JWT_SECRET_KEY
  |                                |   sets exp = now + 24h         |
  |<-- 200 { access_token, ... } --|                                |
```

If the email doesn't exist **or** the password is wrong, the response is always `401 Invalid credentials.` — deliberately the same message to prevent email enumeration.

---

## The JWT

The token is a standard HS256 JWT. Its payload:

```json
{
  "sub":   "<admin UUID>",
  "email": "admin@hamilton.edu",
  "role":  "admin",
  "iat":   1773189217,
  "exp":   1773275617
}
```

- Signed with `JWT_SECRET_KEY` (from `backend/.env`)
- Expires 24 hours after issue (controlled by `JWT_TTL_HOURS` env var)
- Decode without a library: `echo "<token>" | cut -d. -f2 | python3 -c "import base64,sys; s=sys.stdin.read().strip(); print(base64.urlsafe_b64decode(s+'='*(-len(s)%4)).decode())" | jq .`

---

## Protecting a Route

Import `require_jwt` and add it as a `Depends`:

```python
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims

@router.get("/admin/something")
def my_route(claims: JWTClaims = Depends(require_jwt(required_roles=["admin"]))):
    # claims.sub      → admin UUID
    # claims.email    → admin email
    # claims.role     → "admin"
    ...
```

If the `Authorization: Bearer <token>` header is missing → `401`.
If the token is invalid or expired → `401`.
If the role doesn't match → `403`.

---

## API Endpoints

### `POST /api/auth/admin/login`
No auth required. Issues a JWT.

**Request:**
```json
{ "email": "admin@hamilton.edu", "password": "..." }
```

**Response (200):**
```json
{
  "access_token": "eyJ...",
  "token_type":   "bearer",
  "role":         "admin",
  "entity_id":    "<uuid>"
}
```

**Response (401):**
```json
{ "detail": "Invalid credentials." }
```

---

### `POST /api/auth/admin/create`
Requires a valid admin JWT. Creates another admin.

**Headers:** `Authorization: Bearer <token>`

**Request:**
```json
{ "email": "newadmin@hamilton.edu", "password": "..." }
```

**Response (200):**
```json
{ "admin_id": "<uuid>" }
```

---

## Database

```sql
create table public.admins (
    id            uuid primary key default gen_random_uuid(),
    email         text not null unique,
    password_hash text not null,   -- bcrypt hash, never plaintext
    created_at    timestamptz not null default now()
);
```

Passwords are hashed with bcrypt (cost factor from `bcrypt.gensalt()` default, currently 12). The plaintext password is never stored or logged.

---

## First Admin (Bootstrap)

The database starts empty — there's no default admin. Create the first one with the CLI script:

```bash
cd backend
python scripts/create_admin.py --email admin@hamilton.edu
# prompts for password securely via getpass
```

Or pass the password directly (less secure, visible in shell history):

```bash
python scripts/create_admin.py --email admin@hamilton.edu --password mypassword
```

After that, use `POST /api/auth/admin/create` (with a valid JWT) to add more admins.

---

## Environment Variables

Add these to `backend/.env`:

```
JWT_SECRET_KEY=<long random string>   # required — keep secret
JWT_TTL_HOURS=24                      # optional — default 24
```

Generate a good secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## File Map

```
backend/
├── app/
│   ├── auth/
│   │   ├── password.py       # hash_password(), verify_password()
│   │   ├── jwt_utils.py      # JWTClaims, encode_jwt(), decode_jwt()
│   │   └── dependencies.py   # require_jwt() dependency factory
│   ├── routers/
│   │   └── auth.py           # /api/auth/* route handlers
│   └── config.py             # jwt_secret_key, jwt_ttl_hours settings
├── scripts/
│   └── create_admin.py       # first-admin bootstrap CLI
└── tests/
    └── test_auth.py          # integration tests
supabase/migrations/
└── 20260310000000_auth_tables.sql   # admins table
```
