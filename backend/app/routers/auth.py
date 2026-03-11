from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import cast

from app.auth.dependencies import require_admin_jwt
from app.auth.jwt_utils import JWTClaims, encode_jwt
from app.auth.password import hash_password, verify_password
from app.supabase_io.client import supabase

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str


class CreateAdminRequest(BaseModel):
    email: str
    password: str


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
