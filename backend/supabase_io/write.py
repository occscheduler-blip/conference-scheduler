from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time
import re
from typing import Any

import numpy as np
import pandas as pd
from app.config import get_settings

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, label: str) -> str:
    if not value or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            f"Invalid {label}: {value!r}. Use letters/numbers/underscore and avoid leading digits."
        )
    return value


def _resolve_db_url(db_url: str | None = None) -> str:
    resolved = db_url or get_settings().supabase_db_url
    if not resolved:
        raise RuntimeError("Supabase DB URL is missing. Set SUPABASE_DB_URL.")
    return resolved


def _require_psycopg():
    try:
        import psycopg  # type: ignore

        return psycopg
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("psycopg is required for SQL operations. Install psycopg[binary].") from exc


@contextmanager
def _connection(db_url: str):
    psycopg = _require_psycopg()
    with psycopg.connect(db_url, autocommit=True) as conn:
        yield conn


def _normalize_value(value: Any) -> Any:
    if value is None or value is pd.NaT:
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, np.generic):
        return value.item()

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


def _dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = df.to_dict(orient="records")
    return [
        {str(column): _normalize_value(raw_value) for column, raw_value in row.items()}
        for row in records
    ]


def _build_insert_sql(schema: str, table_name: str, columns: list[str]) -> str:
    columns_csv = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"""
    INSERT INTO {schema}.{table_name} ({columns_csv})
    VALUES ({placeholders})
    """


def insert_records(
    table_name: str,
    records: list[dict[str, Any]],
    *,
    schema: str = "public",
    db_url: str | None = None,
    conn: Any | None = None,
) -> int:
    """Insert records into a table using a generic SQL INSERT statement."""
    table_name = _validate_identifier(table_name, "table name")
    schema = _validate_identifier(schema, "schema")

    if not records:
        return 0

    columns = [str(column) for column in records[0].keys()]
    if not columns:
        raise ValueError("records must include at least one column.")
    for column in columns:
        _validate_identifier(column, "column name")

    normalized_rows: list[tuple[Any, ...]] = []
    for row in records:
        normalized_rows.append(tuple(_normalize_value(row.get(column)) for column in columns))

    insert_sql = _build_insert_sql(schema=schema, table_name=table_name, columns=columns)

    if conn is not None:
        with conn.cursor() as cur:
            cur.executemany(insert_sql, normalized_rows)
        return len(normalized_rows)

    resolved_db_url = _resolve_db_url(db_url)
    with _connection(resolved_db_url) as managed_conn:
        with managed_conn.cursor() as cur:
            cur.executemany(insert_sql, normalized_rows)
    return len(normalized_rows)


def append_dataframe(
    df: pd.DataFrame,
    table_name: str,
    *,
    schema: str = "public",
    chunk_size: int = 1_000,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Append rows from a pandas DataFrame into an existing Supabase table.

    Column names in `df` are used directly as destination column names.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    table_name = _validate_identifier(table_name, "table name")
    schema = _validate_identifier(schema, "schema")

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if df.empty:
        return {
            "status": "no-op",
            "schema": schema,
            "table": table_name,
            "rows_inserted": 0,
        }

    records = _dataframe_to_records(df)
    rows_inserted = 0
    for start in range(0, len(records), chunk_size):
        chunk = records[start : start + chunk_size]
        rows_inserted += insert_records(
            table_name=table_name,
            records=chunk,
            schema=schema,
            db_url=db_url,
        )

    return {
        "status": "inserted",
        "schema": schema,
        "table": table_name,
        "rows_inserted": rows_inserted,
        "columns": list(df.columns),
    }


def write_dataframe(
    df: pd.DataFrame,
    table_name: str,
    *,
    schema: str = "public",
    chunk_size: int = 1_000,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Alias for append_dataframe for simpler call sites."""
    return append_dataframe(
        df,
        table_name,
        schema=schema,
        chunk_size=chunk_size,
        db_url=db_url,
    )
