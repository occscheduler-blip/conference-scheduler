import time

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger("main")

from app.routers.events import router as events_router
from app.security import require_api_key

settings = get_settings()
app = FastAPI(title=settings.app_name)

logger.info(
    "Starting %s (env=%s, log_level=%s)",
    settings.app_name,
    settings.app_env,
    settings.log_level,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = (time.time() - start) * 1000
    logger.info(
        "%s %s → %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        ms,
    )
    return response


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "environment": settings.app_env}


app.include_router(
    events_router,
    prefix="/api",
    dependencies=[Depends(require_api_key)],
)
