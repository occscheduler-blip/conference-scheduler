import logging
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.events import router as events_router

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Response:
    start = time.perf_counter()
    logger.info("%s %s", request.method, request.url.path)
    try:
        response: Response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error during %s %s", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.on_event("startup")
def log_startup() -> None:
    logger.info("Starting %s  env=%s  port=%s", settings.app_name, settings.app_env, settings.app_port)
    logger.info("CORS origins: %s", settings.cors_origins)
    logger.info("Supabase URL configured: %s", bool(settings.supabase_url))


@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


app.include_router(auth_router, prefix="/api")

app.include_router(
    events_router,
    prefix="/api",
)
