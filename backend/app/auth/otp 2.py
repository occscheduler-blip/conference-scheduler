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


def _parse_db_datetime(value: object) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    if "." in text:
        main, fractional = text.split(".", 1)
        tz_sign_index = max(fractional.rfind("+"), fractional.rfind("-"))
        if tz_sign_index != -1:
            frac_part = fractional[:tz_sign_index]
            tz_part = fractional[tz_sign_index:]
        else:
            frac_part = fractional
            tz_part = ""
        if frac_part.isdigit():
            text = f"{main}.{frac_part[:6].ljust(6, '0')}{tz_part}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _delete_expired_otps() -> None:
    """Delete all OTP rows that have passed their expiry time."""
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("otp_tokens").delete().lt("expires_at", now).execute()


def store_otp(email: str, code: str, role: str) -> None:
    """Delete any existing unused OTPs for this email+role, clean up expired rows, then insert a new one."""
    supabase.table("otp_tokens").delete().eq("email", email).eq("role", role).eq("used", False).execute()
    _delete_expired_otps()

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
    """Verify the OTP is valid and unexpired, then delete it.

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
    expires_at = _parse_db_datetime(row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP.",
        )

    supabase.table("otp_tokens").delete().eq("id", str(row["id"])).execute()
