import logging
import threading
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.request_context import RequestIdFilter, request_id_middleware
from app.routers.auth import router as auth_router
from app.routers.events import router as events_router

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [%(request_id)s]  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Inject the request id into every log record (default "-" outside requests).
_request_id_filter = RequestIdFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_request_id_filter)
logger = logging.getLogger("app")

settings = get_settings()
app = FastAPI(title=settings.app_name)
_diagnostic_jobs: dict[str, dict[str, Any]] = {}
_diagnostic_jobs_lock = threading.Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Per-request id (must be registered before the logging middleware so the
# id is populated by the time we log).
app.middleware("http")(request_id_middleware)


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


def _clamp_diagnostic_seconds(seconds: int) -> int:
    return max(1, min(seconds, 120))


@app.get("/diagnostics/sleep", tags=["diagnostics"])
def diagnostic_sleep(seconds: int = 60) -> dict[str, object]:
    """Block one HTTP request long enough to verify platform request timeouts."""
    duration = _clamp_diagnostic_seconds(seconds)
    started_at = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at))
    time.sleep(duration)
    ended_at = time.time()
    ended_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended_at))
    return {
        "status": "completed",
        "requested_seconds": seconds,
        "slept_seconds": duration,
        "started_at": started_iso,
        "ended_at": ended_iso,
        "elapsed_seconds": round(ended_at - started_at, 3),
    }


def _run_diagnostic_job(job_id: str, seconds: int) -> None:
    started_at = time.time()
    with _diagnostic_jobs_lock:
        _diagnostic_jobs[job_id].update(
            {
                "status": "running",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at)),
            }
        )

    time.sleep(seconds)

    ended_at = time.time()
    with _diagnostic_jobs_lock:
        _diagnostic_jobs[job_id].update(
            {
                "status": "completed",
                "ended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended_at)),
                "elapsed_seconds": round(ended_at - started_at, 3),
            }
        )


@app.post("/diagnostics/sleep_job", tags=["diagnostics"])
def start_diagnostic_sleep_job(seconds: int = 60) -> dict[str, object]:
    """Start a sleep in a background thread so polling can prove the process finished."""
    duration = _clamp_diagnostic_seconds(seconds)
    job_id = str(uuid4())
    with _diagnostic_jobs_lock:
        _diagnostic_jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "requested_seconds": seconds,
            "sleep_seconds": duration,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "started_at": None,
            "ended_at": None,
            "elapsed_seconds": None,
        }

    thread = threading.Thread(target=_run_diagnostic_job, args=(job_id, duration), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "pending", "poll_url": f"/diagnostics/sleep_job/{job_id}"}


@app.get("/diagnostics/sleep_job/{job_id}", tags=["diagnostics"])
def get_diagnostic_sleep_job(job_id: str) -> dict[str, object]:
    with _diagnostic_jobs_lock:
        job = _diagnostic_jobs.get(job_id)
        if job is None:
            return {"job_id": job_id, "status": "not_found"}
        return dict(job)


app.include_router(auth_router, prefix="/api")

app.include_router(
    events_router,
    prefix="/api",
)
