# Authentication

## Two Independent Systems

The app has two auth systems that coexist without interfering:

| System | Header | Used on | Validated by |
|--------|--------|---------|--------------|
| API Key | `X-API-Key: <key>` | `/api/events/*` | `security.py` → `BACKEND_API_KEY` env var |
| JWT Bearer | `Authorization: Bearer <token>` | `/api/auth/*` and any route that opts in | `dependencies.py` → `JWT_SECRET_KEY` env var |

A route can require one, both, or neither. The events router requires only the API key. The admin-create route requires only a JWT. Nothing currently requires both.

---

## System 1 — API Key (`X-API-Key`)

### How it works

Every request to `/api/events/*` must include:
```
X-API-Key: <value of BACKEND_API_KEY in .env>
```

The dependency in `backend/app/security.py` checks this on every call:

```
Request → require_api_key() → compare header against BACKEND_API_KEY
                            ├─ match   → continue
                            ├─ no match → 401 Invalid API key.
                            └─ key not configured → 500
```

### Who uses it

All frontend API calls include this header. It's a shared secret — everyone with the key has the same access level. There are no per-user permissions in this system.

### Adding it to a new route

The events router is registered with it applied globally:
```python
app.include_router(events_router, prefix="/api", dependencies=[Depends(require_api_key)])
```

To protect a new router the same way, add `dependencies=[Depends(require_api_key)]` to its `include_router` call.

---

## System 2 — JWT Bearer (Admin)

### How it works

```
1. Admin calls POST /api/auth/admin/login with { email, password }
2. Backend looks up email in the admins table
3. bcrypt verifies the password against the stored hash
4. If valid, backend signs a JWT with JWT_SECRET_KEY (HS256, 24h TTL)
5. Admin stores the token and sends it as Authorization: Bearer <token>
6. Protected routes call decode_jwt() which verifies the signature and expiry
```

### The JWT payload

```json
{
  "sub":   "<admin UUID>",
  "email": "admin@hamilton.edu",
  "role":  "admin",
  "iat":   1773189217,
  "exp":   1773275617
}
```

`exp` is always `iat + JWT_TTL_HOURS * 3600`. Default TTL is 24 hours.

### Decode a token manually (for debugging)

```bash
python3 -c "
import base64, sys, json
p = sys.argv[1].split('.')[1]
print(json.dumps(json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4))), indent=2))
" "eyJ..."
```

### Error responses

| Situation | Status | Detail |
|-----------|--------|--------|
| Bad email or bad password | 401 | `"Invalid credentials."` (same message for both — prevents email enumeration) |
| No `Authorization` header | 401 | `"Missing or invalid Authorization header."` |
| Malformed or expired token | 401 | `"Invalid or expired token."` |
| Valid token, wrong role | 403 | `"Insufficient permissions."` |

---

## API Endpoints

### `POST /api/auth/admin/login` — public, no auth required

**Request:**
```json
{ "email": "admin@hamilton.edu", "password": "..." }
```

**200 OK:**
```json
{
  "access_token": "eyJ...",
  "token_type":   "bearer",
  "role":         "admin",
  "entity_id":    "<admin-uuid>"
}
```

**401:**
```json
{ "detail": "Invalid credentials." }
```

---

### `POST /api/auth/admin/create` — requires admin JWT

Creates an additional admin. Only an existing admin can call this.

**Headers:** `Authorization: Bearer <token>`

**Request:**
```json
{ "email": "newadmin@hamilton.edu", "password": "..." }
```

**200 OK:**
```json
{ "admin_id": "<new-admin-uuid>" }
```

---

## Protecting a Route with JWT

Import the dependency factory and declare it in your route:

```python
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims

@router.get("/admin/something")
def my_route(claims: JWTClaims = Depends(require_jwt(required_roles=["admin"]))):
    print(claims.sub)    # admin UUID
    print(claims.email)  # admin@hamilton.edu
    print(claims.role)   # "admin"
```

To allow any valid JWT regardless of role, omit `required_roles`:
```python
claims: JWTClaims = Depends(require_jwt())
```

To apply JWT auth to an entire router:
```python
app.include_router(my_router, prefix="/api", dependencies=[Depends(require_jwt(required_roles=["admin"]))])
```

---

## Database

Admins are stored in a dedicated table, separate from all other tables:

```sql
create table public.admins (
    id            uuid primary key default gen_random_uuid(),
    email         text not null unique,
    password_hash text not null,    -- bcrypt, never plaintext
    created_at    timestamptz not null default now()
);
```

Passwords are hashed with bcrypt at cost factor 12 (library default). The plaintext password is never stored, logged, or returned by any endpoint.

---

## Creating the First Admin

The database starts with no admins. Use the bootstrap script:

```bash
cd backend
python scripts/create_admin.py --email admin@hamilton.edu
# Password: (prompted securely via getpass)
```

After the first admin exists, subsequent admins can be created via `POST /api/auth/admin/create`.

The script validates that the email ends with `@hamilton.edu` before inserting.

---

## Environment Variables

In `backend/.env`:

```env
BACKEND_API_KEY=<shared key for event routes>
JWT_SECRET_KEY=<long random string — keep secret>
JWT_TTL_HOURS=24
```

Generate a strong JWT secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Code Map

```
backend/app/
├── security.py              # require_api_key() — API key dependency
├── auth/
│   ├── password.py          # hash_password(), verify_password() via bcrypt
│   ├── jwt_utils.py         # JWTClaims model, encode_jwt(), decode_jwt()
│   └── dependencies.py      # require_jwt() factory
├── routers/
│   └── auth.py              # POST /api/auth/admin/login, /admin/create
└── config.py                # jwt_secret_key, jwt_ttl_hours, backend_api_key

backend/scripts/
└── create_admin.py          # first-admin bootstrap CLI

supabase/migrations/
└── 20260310000000_auth_tables.sql   # admins table

backend/tests/
├── conftest.py              # admin_token, admin_headers fixtures
└── test_auth.py             # integration tests
```

---

## Testing

`conftest.py` provides two fixtures for writing tests against auth-protected routes:

```python
def test_something(client, admin_token):
    # admin_token is a valid JWT string
    resp = client.get("/api/something", headers={"Authorization": f"Bearer {admin_token}"})

def test_something_else(client, admin_headers):
    # admin_headers = { "X-API-Key": "...", "Authorization": "Bearer ..." }
    # use this for routes that require both auth systems
    resp = client.get("/api/events/...", headers=admin_headers)
```

The `admin_token` fixture inserts a test admin directly into the database and logs in, returning the JWT. The `clean_db` autouse fixture truncates the `admins` table between every test.
