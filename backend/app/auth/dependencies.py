from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Annotated, Callable

from app.auth.jwt_utils import JWTClaims, decode_jwt

_bearer = HTTPBearer(auto_error=False)


def require_jwt(required_roles: list[str] | None = None) -> Callable[..., object]:
    def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
    ) -> JWTClaims:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization header.",
            )
        claims = decode_jwt(credentials.credentials)
        if required_roles and claims.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return claims

    return dependency
