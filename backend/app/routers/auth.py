from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import cast

from app.auth.dependencies import require_jwt
from app.auth.email import send_otp_email
from app.auth.jwt_utils import JWTClaims, encode_jwt
from app.auth.otp import generate_otp, store_otp, verify_and_consume_otp
from app.auth.password import hash_password, verify_password
from app.supabase_io.client import supabase

router = APIRouter(prefix="/auth", tags=["auth"])

# Roles that can sign in via OTP (admins use password login instead)
_OTP_ROLES = {"department_head", "professor", "student"}

# Which table to look up the email in for each role
_ROLE_TABLE: dict[str, str] = {
    "department_head": "departments",
    "professor": "professors",
    "student": "students",
}

class LoginRequest(BaseModel):
    email: str
    password: str


class CreateAdminRequest(BaseModel):
    email: str
    password: str


@router.post("/admin/login")
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
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
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


# ---------------------------------------------------------------------------
# OTP sign-in (department heads, professors, students)
# ---------------------------------------------------------------------------

class OTPRequestBody(BaseModel):
    email: str
    role: str  # 'department_head' | 'professor' | 'student'


class OTPVerifyBody(BaseModel):
    email: str
    role: str
    otp: str


@router.post("/otp/request", status_code=status.HTTP_200_OK)
def otp_request(body: OTPRequestBody) -> dict[str, str]:
    """Generate a 6-digit OTP and email it to the user.

    The email must already exist in the table for the given role.
    """
    if body.role not in _OTP_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_OTP_ROLES))}",
        )

    table = _ROLE_TABLE[body.role]
    resp = supabase.table(table).select("id").eq("email", body.email).limit(1).execute()
    if not cast(list[dict[str, object]], resp.data or []):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    code = generate_otp()
    store_otp(body.email, code, body.role)
    send_otp_email(body.email, code)

    return {"detail": "OTP sent to your email address."}


@router.post("/otp/verify", status_code=status.HTTP_200_OK)
def otp_verify(body: OTPVerifyBody) -> dict[str, str]:
    """Exchange a valid OTP for a JWT access token."""
    if body.role not in _OTP_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_OTP_ROLES))}",
        )

    verify_and_consume_otp(body.email, body.otp, body.role)

    table = _ROLE_TABLE[body.role]
    resp = supabase.table(table).select("id").eq("email", body.email).limit(1).execute()
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    entity_id = str(rows[0]["id"])
    token = encode_jwt(entity_id, body.email, body.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": body.role,
        "entity_id": entity_id,
    }
