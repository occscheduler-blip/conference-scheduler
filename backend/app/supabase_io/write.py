import pandas as pd
from datetime import date, datetime
from uuid import UUID

from app.supabase_io.client import supabase


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

    resp = supabase.table(table_name).insert(lines).execute()

    return resp
