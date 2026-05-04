"""Per-request context (request id) propagated via contextvars.

A FastAPI middleware (registered in main.py) reads the incoming
``X-Request-Id`` header (or generates a fresh UUID4 if missing), stores it
in this contextvar, and echoes it back as a response header. A logging
filter pulls it into every log record so concurrent writes can be traced
to a specific request.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request, Response

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    incoming = request.headers.get("x-request-id")
    rid = incoming if incoming else uuid4().hex
    token = _request_id_var.set(rid)
    try:
        response: Response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response
    finally:
        _request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the current request id into LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
