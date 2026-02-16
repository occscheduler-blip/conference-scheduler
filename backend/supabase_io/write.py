from __future__ import annotations

import os
import re
import json
from contextlib import contextmanager
from typing import Any, Iterator, Literal

import pandas as pd
from app.config import get_settings

IfExistsMode = Literal["append", "replace", "fail"]
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_psycopg():
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "psycopg is required for SQL writes. Install it with "
            "`./.venv/bin/pip install psycopg[binary]`."
        ) from exc
    return psycopg


def _validate_identifier(value: str, label: str) -> str:
    if not _SAFE_IDENT.match(value):
        raise ValueError(f"Invalid {label} '{value}'. Only letters, digits, and underscores are allowed.")
    return value


def _resolve_db_url(explicit_db_url: str | None = None) -> str:
    if explicit_db_url:
        return explicit_db_url
    settings = get_settings()
    env_db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    db_url = env_db_url or getattr(settings, "supabase_db_url", "")
    if not db_url:
        raise RuntimeError(
            "Missing database connection string. Set SUPABASE_DB_URL (or DATABASE_URL), "
            "or pass db_url explicitly."
        )
    return db_url


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, (pd.Timedelta,)):
        return str(value)
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, default=str)
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            return value
    return value


@contextmanager
def _connection(db_url: str, *, autocommit: bool = False) -> Iterator[Any]:
    psycopg = _require_psycopg()
    with psycopg.connect(db_url, autocommit=autocommit) as conn:
        yield conn


def write_validated_records(
    records_by_table: dict[str, list[dict[str, Any]]],
    *,
    schema: str = "public",
    allowed_tables: set[str] | None = None,
    db_url: str | None = None,
) -> dict[str, int]:
    """Insert pre-validated rows into existing tables.

    This function assumes payload shape/content was validated upstream and only
    performs structural and safety checks before writing.
    """
    if not records_by_table:
        raise ValueError("records_by_table cannot be empty.")

    schema = _validate_identifier(schema, "schema")
    db_url = _resolve_db_url(db_url)
    psycopg = _require_psycopg()
    inserted_counts: dict[str, int] = {}

    with _connection(db_url) as conn:
        with conn.cursor() as cur:
            for table_name, rows in records_by_table.items():
                _validate_identifier(table_name, "table name")
                if allowed_tables is not None and table_name not in allowed_tables:
                    raise ValueError(f"Unsupported table '{table_name}'.")
                if not isinstance(rows, list) or not rows:
                    raise ValueError(f"Table '{table_name}' must include a non-empty list of rows.")
                if any(not isinstance(row, dict) for row in rows):
                    raise ValueError(f"Table '{table_name}' rows must be dictionaries.")

                first_row = rows[0]
                if not first_row:
                    raise ValueError(f"Table '{table_name}' rows must include at least one column.")

                column_names = list(first_row.keys())
                normalized_columns = [_validate_identifier(str(col), "column name") for col in column_names]
                expected_columns = set(column_names)
                for row in rows:
                    if set(row.keys()) != expected_columns:
                        raise ValueError(f"All rows for table '{table_name}' must have identical columns.")

                values_placeholder = psycopg.sql.SQL(", ").join(
                    psycopg.sql.Placeholder() for _ in normalized_columns
                )
                insert_sql = psycopg.sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    psycopg.sql.Identifier(schema, table_name),
                    psycopg.sql.SQL(", ").join(
                        psycopg.sql.Identifier(column_name) for column_name in normalized_columns
                    ),
                    values_placeholder,
                )
                params = [
                    tuple(_normalize_value(row[column_name]) for column_name in column_names)
                    for row in rows
                ]
                cur.executemany(insert_sql, params)
                inserted_counts[table_name] = len(rows)

    return inserted_counts