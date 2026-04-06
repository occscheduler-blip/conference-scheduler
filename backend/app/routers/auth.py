import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import cast

from app.auth.dependencies import require_jwt
from app.auth.email import send_otp_email
from app.auth.jwt_utils import JWTClaims, encode_jwt
from app.auth.otp import generate_otp, store_otp, verify_and_consume_otp
from app.auth.password import hash_password, verify_password
from app.supabase_io.client import supabase

logger = logging.getLogger(__name__)

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
    logger.info("Admin login attempt for email=%s", body.email)
    resp = supabase.table("admins").select("*").eq("email", body.email).execute()
    rows = cast(list[dict[str,object]], resp.data or [])

    if not rows or not verify_password(body.password, str(rows[0]["password_hash"])):
        logger.warning("Admin login failed for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    admin = rows[0]
    token = encode_jwt(str(admin["id"]), str(admin["email"]), "admin")
    logger.info("Admin login successful for email=%s  admin_id=%s", body.email, admin["id"])
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
    logger.info("Creating new admin with email=%s", body.email)
    resp = (
        supabase.table("admins")
        .insert({"email": body.email, "password_hash": password_hash})
        .execute()
    )
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        logger.error("Failed to create admin for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create admin.",
        )
    logger.info("Admin created: admin_id=%s  email=%s", rows[0]["id"], body.email)
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
    logger.info("OTP request: role=%s  email=%s", body.role, body.email)
    if body.role not in _OTP_ROLES:
        logger.warning("OTP request with invalid role=%s  email=%s", body.role, body.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_OTP_ROLES))}",
        )

    table = _ROLE_TABLE[body.role]
    resp = supabase.table(table).select("id").eq("email", body.email).limit(1).execute()
    if not cast(list[dict[str, object]], resp.data or []):
        logger.warning("OTP request for unknown email=%s  role=%s", body.email, body.role)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    code = generate_otp()
    store_otp(body.email, code, body.role)
    send_otp_email(body.email, code)
    logger.info("OTP sent to email=%s  role=%s", body.email, body.role)

    return {"detail": "OTP sent to your email address."}


@router.post("/otp/verify", status_code=status.HTTP_200_OK)
def otp_verify(body: OTPVerifyBody) -> dict[str, str]:
    """Exchange a valid OTP for a JWT access token."""
    logger.info("OTP verify: role=%s  email=%s", body.role, body.email)
    if body.role not in _OTP_ROLES:
        logger.warning("OTP verify with invalid role=%s  email=%s", body.role, body.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_OTP_ROLES))}",
        )

    verify_and_consume_otp(body.email, body.otp, body.role)

    table = _ROLE_TABLE[body.role]
    resp = supabase.table(table).select("id").eq("email", body.email).limit(1).execute()
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        logger.warning("OTP verify: email=%s not found in %s after OTP consumed", body.email, table)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    entity_id = str(rows[0]["id"])
    token = encode_jwt(entity_id, body.email, body.role)
    logger.info("OTP login successful: role=%s  email=%s  entity_id=%s", body.role, body.email, entity_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": body.role,
        "entity_id": entity_id,
    }
