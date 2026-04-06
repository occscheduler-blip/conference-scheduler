import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Annotated, Callable

from app.auth.jwt_utils import JWTClaims, decode_jwt

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def require_jwt(required_roles: list[str] | None = None) -> Callable[..., object]:
    def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
    ) -> JWTClaims:
        if not credentials:
            logger.warning("JWT auth failed: missing Authorization header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization header.",
            )
        claims = decode_jwt(credentials.credentials)
        if required_roles and claims.role not in required_roles:
            logger.warning(
                "JWT auth forbidden: role=%s not in %s  sub=%s",
                claims.role, required_roles, claims.sub,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        logger.debug("JWT auth ok: sub=%s  role=%s", claims.sub, claims.role)
        return claims

    return dependency
