import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Mapping
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


def update_column_by_ids(
    table_name: str,
    column: str,
    id_to_value: Mapping[UUID, str | int | None],
) -> int:
    """Batch-update one column across many rows.

    Groups ids by value and issues one ``update(...).in_("id", bucket)`` per
    distinct value — so N rows with V distinct values becomes V queries
    instead of N.
    """
    if not id_to_value:
        return 0

    buckets: dict[str | int | None, list[str]] = defaultdict(list)
    for uid, value in id_to_value.items():
        buckets[value].append(str(uid))

    logger.info(
        "UPDATE %s.%s: %d row(s) across %d distinct value(s)",
        table_name, column, len(id_to_value), len(buckets),
    )

    total = 0
    for value, ids in buckets.items():
        try:
            resp = (
                supabase.table(table_name)
                .update({column: value})
                .in_("id", ids)
                .execute()
            )
        except Exception:
            logger.exception("UPDATE %s.%s failed", table_name, column)
            raise
        total += len(resp.data or [])
    return total
