from fastapi import Header, HTTPException, status
from typing import Callable

from app.auth.jwt_utils import JWTClaims, decode_jwt


def require_jwt(required_roles: list[str] | None = None) -> Callable[..., object]:
    def dependency(authorization: str | None = Header(default=None)) -> JWTClaims:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization header.",
            )
        claims = decode_jwt(authorization.removeprefix("Bearer "))
        if required_roles and claims.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return claims

    return dependency
