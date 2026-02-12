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


def _pg_type_for_series(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TIMESTAMPTZ"
    return "TEXT"


@contextmanager
def _connection(db_url: str, *, autocommit: bool = False) -> Iterator[Any]:
    psycopg = _require_psycopg()
    with psycopg.connect(db_url, autocommit=autocommit) as conn:
        yield conn


def write(
    df: pd.DataFrame,
    table_name: str,
    *,
    schema: str = "public",
    if_exists: IfExistsMode = "append",
    db_url: str | None = None,
) -> int:
    """Write a dataframe to a Postgres table using SQL.

    Args:
        df (pd.DataFrame): the dataframe to write.
        table_name (str): the destination table name.
        schema (str, optional): the destination schema. Defaults to "public".
        if_exists (IfExistsMode, optional): behavior when table exists ("append", "replace", or "fail").
        db_url (str | None, optional): explicit Postgres connection URL. If omitted, uses env/config.

    Returns:
        int: the number of rows written.
    """
    if df.empty:
        return 0
    if if_exists not in {"append", "replace", "fail"}:
        raise ValueError("if_exists must be one of: 'append', 'replace', 'fail'.")

    schema = _validate_identifier(schema, "schema")
    table_name = _validate_identifier(table_name, "table name")
    db_url = _resolve_db_url(db_url)
    psycopg = _require_psycopg()

    normalized_df = df.copy()
    normalized_df.columns = [_validate_identifier(str(col), "column name") for col in normalized_df.columns]

    with _connection(db_url) as conn:
        with conn.cursor() as cur:
            table_ident = psycopg.sql.Identifier(schema, table_name)
            cur.execute(
                psycopg.sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    psycopg.sql.Identifier(schema)
                )
            )

            if if_exists == "replace":
                cur.execute(
                    psycopg.sql.SQL("DROP TABLE IF EXISTS {}").format(table_ident)
                )
            elif if_exists == "fail":
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    LIMIT 1
                    """,
                    (schema, table_name),
                )
                if cur.fetchone():
                    raise ValueError(f"Table {schema}.{table_name} already exists.")

            column_defs = []
            for column_name in normalized_df.columns:
                column_type = _pg_type_for_series(normalized_df[column_name])
                column_defs.append(
                    psycopg.sql.SQL("{} {}").format(
                        psycopg.sql.Identifier(column_name),
                        psycopg.sql.SQL(column_type),
                    )
                )

            cur.execute(
                psycopg.sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                    table_ident,
                    psycopg.sql.SQL(", ").join(column_defs),
                )
            )

            insert_columns = [psycopg.sql.Identifier(col) for col in normalized_df.columns]
            values_placeholder = psycopg.sql.SQL(", ").join(
                psycopg.sql.Placeholder() for _ in normalized_df.columns
            )
            insert_sql = psycopg.sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                table_ident,
                psycopg.sql.SQL(", ").join(insert_columns),
                values_placeholder,
            )

            rows = [
                tuple(_normalize_value(value) for value in row)
                for row in normalized_df.itertuples(index=False, name=None)
            ]
            cur.executemany(insert_sql, rows)

    return len(normalized_df.index)


def create_database(
    database_name: str,
    *,
    admin_db_url: str | None = None,
) -> None:
    """
    Create a new Postgres database using SQL.

    Note: On Supabase, CREATE DATABASE generally requires admin-level privileges and
    may be disallowed on hosted projects. In that case, this raises a RuntimeError.
    """
    database_name = _validate_identifier(database_name, "database name")
    db_url = _resolve_db_url(admin_db_url)
    psycopg = _require_psycopg()

    try:
        with _connection(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    psycopg.sql.SQL("CREATE DATABASE {}").format(
                        psycopg.sql.Identifier(database_name)
                    )
                )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to create database '{database_name}'. "
            "Your Supabase role may not have CREATE DATABASE privileges."
        ) from exc


def delete_by_id(
    table_name: str,
    row_id: int,
    *,
    id_column: str = "id",
    schema: str = "public",
    db_url: str | None = None,
) -> int:
    """Delete rows from a table by an id value.

    Args:
        table_name (str): the destination table name.
        row_id (int): the id value to delete.
        id_column (str, optional): the id column name. Defaults to "id".
        schema (str, optional): the destination schema. Defaults to "public".
        db_url (str | None, optional): explicit Postgres connection URL. If omitted, uses env/config.

    Returns:
        int: the number of rows deleted.
    """
    schema = _validate_identifier(schema, "schema")
    table_name = _validate_identifier(table_name, "table name")
    id_column = _validate_identifier(id_column, "id column")
    db_url = _resolve_db_url(db_url)
    psycopg = _require_psycopg()

    with _connection(db_url) as conn:
        with conn.cursor() as cur:
            delete_sql = psycopg.sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                psycopg.sql.Identifier(schema, table_name),
                psycopg.sql.Identifier(id_column),
            )
            cur.execute(delete_sql, (row_id,))
            deleted_rows = cur.rowcount or 0
    return deleted_rows

