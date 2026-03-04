import logging

from fastapi import Header, HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> None:
    settings = get_settings()

    if not settings.backend_api_key:
        logger.error("BACKEND_API_KEY is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key auth is enabled but BACKEND_API_KEY is not configured.",
        )

    if x_api_key != settings.backend_api_key:
        hint = x_api_key[:4] + "…" if x_api_key and len(x_api_key) > 4 else "<missing>"
        logger.warning("Rejected request with invalid API key: %s", hint)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
