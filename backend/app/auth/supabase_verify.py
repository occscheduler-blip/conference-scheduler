from typing import Any

from fastapi import HTTPException, status

from app.supabase_io.client import supabase


def get_supabase_user(token: str) -> Any:
    """Verify a Supabase-issued JWT and return the authenticated user."""
    try:
        response = supabase.auth.get_user(jwt=token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc
    if response.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )
    return response.user
