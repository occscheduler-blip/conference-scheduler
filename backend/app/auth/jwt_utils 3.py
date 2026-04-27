import time

from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings

_ALGORITHM = "HS256"


class JWTClaims(BaseModel):
    sub: str    # admin UUID as string
    email: str
    role: str   # "admin" (only role issued here for now)
    iat: int
    exp: int


def encode_jwt(entity_id: str, email: str, role: str) -> str:
    settings = get_settings()
    now = int(time.time())
    claims = {
        "sub": entity_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + settings.jwt_ttl_hours * 3600,
    }
    return str(jwt.encode(claims, settings.jwt_secret_key, algorithm=_ALGORITHM))


def decode_jwt(token: str) -> JWTClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALGORITHM])
        return JWTClaims(**payload)
    except (JWTError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
