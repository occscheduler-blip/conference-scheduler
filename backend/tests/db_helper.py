"""Psycopg helper for inspecting and cleaning the local test database."""
import os
from typing import Any
import psycopg
from psycopg.rows import dict_row

_DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# Truncation order respects FK deps (children before parents)
_TRUNCATE_ORDER = [
    "requests", "presenting_students", "timeframes",
    "students", "professors", "presentations",
    "classes", "departments", "symposiums",
    "admins",
]


class DbHelper:
    def __init__(self) -> None:
        # Use TEST_DB_URL to avoid picking up the production SUPABASE_DB_URL
        url = os.environ.get("TEST_DB_URL", _DEFAULT_DB_URL)
        self._conn = psycopg.connect(url, row_factory=dict_row)
        self._conn.autocommit = True

    def count(self, table: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM public.{table}")
            row = cur.fetchone()
            return int(row["n"]) if row else 0

    def rows(self, table: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT * FROM public.{table}")
            return cur.fetchall()

    def truncate_all(self) -> None:
        tables = ", ".join(f"public.{t}" for t in _TRUNCATE_ORDER)
        with self._conn.cursor() as cur:
            cur.execute(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")

    def close(self) -> None:
        self._conn.close()
