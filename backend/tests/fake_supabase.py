"""In-memory Supabase client that mirrors the real supabase-py fluent API.

Use the ``fake_supabase`` fixture (conftest.py) in integration tests so that
real data flows through the full router → supabase_io → in-memory storage
stack without needing a live database.

Supported query pattern::

    client.table("students")
          .select("*")          # or .insert([...]) / .update({}) / .delete()
          .eq("class_id", uid)  # zero or more filters
          .in_("id", [uid1])
          .limit(10)
          .execute()            # → SimpleNamespace(data=[...], count=N)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

class FakeQueryBuilder:
    """Accumulates filter calls then executes against an in-memory list."""

    def __init__(
        self,
        table_data: list[dict[str, Any]],
        operation: str,
        payload: Any = None,
        count_mode: bool = False,
    ) -> None:
        self._table_data = table_data
        self._operation = operation
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._count_mode = count_mode

    # ── filter methods ────────────────────────────────────────────────────

    def eq(self, column: str, value: Any) -> "FakeQueryBuilder":
        self._filters.append((column, "eq", value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQueryBuilder":
        self._filters.append((column, "in_", values))
        return self

    def limit(self, _n: int) -> "FakeQueryBuilder":
        return self

    # ── internal helpers ──────────────────────────────────────────────────

    def _matches(self, row: dict[str, Any]) -> bool:
        for col, op, val in self._filters:
            row_val = row.get(col)
            if op == "eq":
                if str(row_val) != str(val):
                    return False
            elif op == "in_":
                if str(row_val) not in [str(v) for v in val]:
                    return False
        return True

    # ── execute ───────────────────────────────────────────────────────────

    def execute(self) -> SimpleNamespace:
        if self._operation == "select":
            matched = [r for r in self._table_data if self._matches(r)]
            count = len(matched) if self._count_mode else None
            return SimpleNamespace(data=matched, count=count)

        if self._operation == "insert":
            rows: list[dict[str, Any]] = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            inserted: list[dict[str, Any]] = []
            for row in rows:
                new_row = dict(row)
                if not new_row.get("id"):
                    new_row["id"] = str(uuid4())
                self._table_data.append(new_row)
                inserted.append(new_row)
            return SimpleNamespace(data=inserted, count=len(inserted))

        if self._operation == "update":
            matched = [r for r in self._table_data if self._matches(r)]
            for row in matched:
                row.update(self._payload)
            return SimpleNamespace(data=matched, count=len(matched))

        if self._operation == "delete":
            matched = [r for r in self._table_data if self._matches(r)]
            for row in matched:
                self._table_data.remove(row)
            return SimpleNamespace(data=matched, count=len(matched))

        return SimpleNamespace(data=[], count=0)


# ---------------------------------------------------------------------------
# Table handle
# ---------------------------------------------------------------------------

class FakeTable:
    """Mirrors the table object returned by ``supabase.table(name)``."""

    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data

    def select(self, *_args: Any, count: Any = None) -> FakeQueryBuilder:
        return FakeQueryBuilder(
            self._data, "select", count_mode=(count is not None)
        )

    def insert(self, rows: list[dict[str, Any]] | dict[str, Any]) -> FakeQueryBuilder:
        return FakeQueryBuilder(self._data, "insert", payload=rows)

    def update(self, data: dict[str, Any]) -> FakeQueryBuilder:
        return FakeQueryBuilder(self._data, "update", payload=data)

    def delete(self) -> FakeQueryBuilder:
        return FakeQueryBuilder(self._data, "delete")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class FakeSupabaseClient:
    """Drop-in replacement for the real Supabase client.

    Each table is an in-memory ``list[dict]``.  Use the helper methods to
    seed data before a test and to inspect state afterwards.
    """

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    # ── supabase-py API ───────────────────────────────────────────────────

    def table(self, name: str) -> FakeTable:
        if name not in self._tables:
            self._tables[name] = []
        return FakeTable(self._tables[name])

    # ── test helpers ──────────────────────────────────────────────────────

    def seed(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        """Append rows to a table (creates the table if it doesn't exist)."""
        if table_name not in self._tables:
            self._tables[table_name] = []
        self._tables[table_name].extend([dict(r) for r in rows])

    def rows(self, table_name: str) -> list[dict[str, Any]]:
        """Return a snapshot of the current rows in *table_name*."""
        return list(self._tables.get(table_name, []))

    def count(self, table_name: str) -> int:
        """Return the number of rows currently in *table_name*."""
        return len(self._tables.get(table_name, []))

    def reset(self) -> None:
        """Wipe all tables (called automatically by the fixture between tests)."""
        self._tables.clear()
