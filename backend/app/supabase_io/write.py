import logging
from datetime import date, datetime
from uuid import UUID

from app.supabase_io.client import supabase
from postgrest.base_request_builder import APIResponse

logger = logging.getLogger(__name__)


def _to_json_scalar(value: str | UUID | datetime | date | int | None) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def insert(table_name: str, data: list[dict[str, str | int | UUID | datetime | date | None]]) -> APIResponse:
    logger.info("INSERT %s: %d row(s)", table_name, len(data))
    lines = [{k: _to_json_scalar(v) for k, v in row.items()} for row in data]

    try:
        resp = supabase.table(table_name).insert(lines).execute()
    except Exception:
        logger.exception("INSERT %s failed", table_name)
        raise
    logger.debug("INSERT %s: %d row(s) returned", table_name, len(resp.data or []))
    return resp
