import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import cast

from fastapi import HTTPException, status

from app.supabase_io.client import supabase

OTP_TTL_MINUTES = 10
OTP_DIGITS = 6


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def generate_otp() -> str:
    """Return a zero-padded random 6-digit string."""
    return str(secrets.randbelow(10**OTP_DIGITS)).zfill(OTP_DIGITS)


def store_otp(email: str, code: str, role: str) -> None:
    """Invalidate any existing unused OTPs for this email+role, then insert a new one."""
    supabase.table("otp_tokens").update({"used": True}).eq("email", email).eq("role", role).eq("used", False).execute()

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    supabase.table("otp_tokens").insert(
        {
            "email": email,
            "token_hash": _hash_otp(code),
            "role": role,
            "expires_at": expires_at.isoformat(),
        }
    ).execute()


def verify_and_consume_otp(email: str, code: str, role: str) -> None:
    """Verify the OTP is valid and unexpired, then mark it as used.

    Raises HTTP 401 if the OTP is wrong, already used, or expired.
    """
    resp = (
        supabase.table("otp_tokens")
        .select("id, expires_at")
        .eq("email", email)
        .eq("role", role)
        .eq("token_hash", _hash_otp(code))
        .eq("used", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = cast(list[dict[str, object]], resp.data or [])

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP.",
        )

    row = rows[0]
    expires_str = str(row["expires_at"]).replace("Z", "+00:00")
    expires_at = datetime.fromisoformat(expires_str)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP.",
        )

    supabase.table("otp_tokens").update({"used": True}).eq("id", str(row["id"])).execute()
