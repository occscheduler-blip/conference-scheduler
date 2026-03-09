import pandas as pd
from datetime import date, datetime
from uuid import UUID

from app.supabase_io.client import supabase
from postgrest.base_request_builder import APIResponse


def _to_json_scalar(value: UUID | datetime | date | pd.Timestamp | None) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return value


def insert(table_name: str, data: list[dict[str, UUID | datetime | date | pd.Timestamp | None]]) -> APIResponse:
    lines = [{k: _to_json_scalar(v) for k, v in row.items()} for row in data]

    resp = supabase.table(table_name).insert(lines).execute()

    return resp
