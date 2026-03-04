import pandas as pd
from datetime import date, datetime
from uuid import UUID

from app.logging_config import get_logger
from app.supabase_io.client import supabase

logger = get_logger("supabase_io")


def _to_json_scalar(value):
    if pd.isna(value):
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return value


def insert(table_name: str, data: list[dict]):
    lines = [{k: _to_json_scalar(v) for k, v in row.items()} for row in data]
    logger.debug("insert → %s (%d rows)", table_name, len(lines))
    resp = supabase.table(table_name).insert(lines).execute()
    return resp
