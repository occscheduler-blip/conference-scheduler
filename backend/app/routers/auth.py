from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.dependencies import require_admin_jwt
from app.auth.jwt_utils import JWTClaims, encode_jwt
from app.auth.password import hash_password, verify_password
from app.auth.supabase_verify import get_supabase_user
from app.supabase_io.client import supabase

_bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str


class CreateAdminRequest(BaseModel):
    email: str
    password: str


class RequestOtpRequest(BaseModel):
    email: str


@router.post("/admin/login")
# TODO: Make sure password is sent over a secure connection, if not hash it first.
def admin_login(body: LoginRequest) -> dict[str, str]:
    resp = supabase.table("admins").select("*").eq("email", body.email).execute()
    rows = cast(list[dict[str,object]], resp.data or [])

    if not rows or not verify_password(body.password, str(rows[0]["password_hash"])):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    admin = rows[0]
    token = encode_jwt(str(admin["id"]), str(admin["email"]), "admin")
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "admin",
        "entity_id": str(admin["id"]),
    }


@router.post("/admin/create", status_code=status.HTTP_200_OK)
def admin_create(
    body: CreateAdminRequest,
    _claims: JWTClaims = Depends(require_admin_jwt),
) -> dict[str, str]:
    password_hash = hash_password(body.password)
    resp = (
        supabase.table("admins")
        .insert({"email": body.email, "password_hash": password_hash})
        .execute()
    )
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create admin.",
        )
    return {"admin_id": str(rows[0]["id"])}


@router.post("/request-otp")
def request_otp(body: RequestOtpRequest) -> dict[str, str]:
    """Validate that the email belongs to a known user and return their role."""
    email = body.email.strip().lower()

    if cast(list[object], supabase.table("professors").select("id").eq("email", email).execute().data or []):
        return {"role": "professor"}
    if cast(list[object], supabase.table("students").select("id").eq("email", email).execute().data or []):
        return {"role": "student"}
    if cast(list[object], supabase.table("departments").select("id").eq("email", email).execute().data or []):
        return {"role": "department_head"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Email not registered in the system.",
    )


@router.get("/me")
def get_me(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, object]:
    """Verify a Supabase JWT and return the user's roles and entity IDs."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    user = get_supabase_user(credentials.credentials)
    user_id = str(user.id)
    email = str(user.email or "")

    existing = cast(
        list[dict[str, str]],
        supabase.table("user_roles").select("role, entity_id").eq("user_id", user_id).execute().data or [],
    )
    if existing:
        return {"roles": existing}

    # First sign-in: find this email in professors, students, and departments.
    new_roles: list[dict[str, str]] = []

    for table, role in [("professors", "professor"), ("students", "student")]:
        rows = cast(
            list[dict[str, object]],
            supabase.table(table).select("id").eq("email", email).execute().data or [],
        )
        for row in rows:
            new_roles.append({"user_id": user_id, "role": role, "entity_id": str(row["id"])})

    dept_rows = cast(
        list[dict[str, object]],
        supabase.table("departments").select("id").eq("email", email).execute().data or [],
    )
    for row in dept_rows:
        new_roles.append({"user_id": user_id, "role": "department_head", "entity_id": str(row["id"])})

    if not new_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No roles found for this email.",
        )

    supabase.table("user_roles").insert(new_roles).execute()
    return {"roles": [{"role": r["role"], "entity_id": r["entity_id"]} for r in new_roles]}
