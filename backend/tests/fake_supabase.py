"""In-memory Supabase client that mirrors the real supabase-py fluent API.

Use the ``fake_supabase`` fixture (conftest.py) in integration tests so that
real data flows through the full router → supabase_io → in-memory storage
stack without needing a live database.

Supported query patterns::

    client.table("departments")
          .select("*")                        # flat select
          .select("*, classes(*)")            # PostgREST nested select (1 level)
          .select("*, classes(*, profs(*))")  # PostgREST nested select (2 levels)
          .eq("symposium_id", uid)
          .in_("id", [uid1, uid2])
          .limit(10)
          .execute()                          # → SimpleNamespace(data=[...], count=N)

Nested selects use the FK_MAP table below to resolve parent→child joins.
Timeframes are intentionally excluded (polymorphic linked_id, no FK).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4


# ---------------------------------------------------------------------------
# FK relationship map for nested select resolution
# (parent_table, child_relation) → (parent_pk_col, child_fk_col)
# ---------------------------------------------------------------------------

FK_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("symposiums", "departments"):          ("id", "symposium_id"),
    ("departments", "classes"):             ("id", "department_id"),
    ("classes", "professors"):              ("id", "class_id"),
    ("classes", "students"):               ("id", "class_id"),
    ("classes", "presentations"):           ("id", "class_id"),
    ("presentations", "presenting_students"): ("id", "presentation_id"),
    ("students", "requests"):              ("id", "student_id"),
}


# ---------------------------------------------------------------------------
# Select string parser
# ---------------------------------------------------------------------------

def _parse_nested_relations(select_str: str) -> list[tuple[str, str]]:
    """Parse a PostgREST select string into (relation_name, inner_select) pairs.

    Example:
        "*, classes(*, professors(*), students(*))"
        → [("classes", "*, professors(*), students(*)")]
    """
    relations: list[tuple[str, str]] = []
    s = select_str.strip()
    i = 0
    while i < len(s):
        # Skip commas and spaces
        if s[i] in (" ", ","):
            i += 1
            continue
        # Skip standalone '*'
        if s[i] == "*" and (i + 1 >= len(s) or s[i + 1] in (" ", ",")):
            i += 1
            continue
        # Read identifier up to '(', ',', or ' '
        j = i
        while j < len(s) and s[j] not in ("(", ",", " "):
            j += 1
        name = s[i:j].strip()
        i = j
        if not name or name == "*":
            continue
        # If followed by '(', extract the inner select via depth-counting
        if i < len(s) and s[i] == "(":
            depth = 0
            k = i
            while k < len(s):
                if s[k] == "(":
                    depth += 1
                elif s[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            inner = s[i + 1 : k]
            relations.append((name, inner))
            i = k + 1
    return relations


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
        select_str: str = "*",
        table_name: str = "",
        client: "FakeSupabaseClient | None" = None,
    ) -> None:
        self._table_data = table_data
        self._operation = operation
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._count_mode = count_mode
        self._select_str = select_str
        self._table_name = table_name
        self._client = client

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

    def _embed_nested(
        self,
        rows: list[dict[str, Any]],
        table_name: str,
        select_str: str,
    ) -> list[dict[str, Any]]:
        """Recursively resolve nested relations and embed them into rows."""
        relations = _parse_nested_relations(select_str)
        if not relations or self._client is None:
            return rows

        rows = [dict(r) for r in rows]  # shallow-copy each row
        for relation_name, inner_select in relations:
            mapping = FK_MAP.get((table_name, relation_name))
            if mapping is None:
                continue
            parent_pk, child_fk = mapping
            child_table_data = self._client._tables.get(relation_name, [])
            for row in rows:
                parent_val = str(row.get(parent_pk, ""))
                children = [
                    dict(c) for c in child_table_data
                    if str(c.get(child_fk, "")) == parent_val
                ]
                # Recurse one level deeper if inner_select has its own relations
                if inner_select.strip() not in ("*", ""):
                    children = self._embed_nested(children, relation_name, inner_select)
                row[relation_name] = children

        return rows

    # ── execute ───────────────────────────────────────────────────────────

    def execute(self) -> SimpleNamespace:
        if self._operation == "select":
            matched = [r for r in self._table_data if self._matches(r)]
            matched = self._embed_nested(matched, self._table_name, self._select_str)
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

    def __init__(
        self,
        data: list[dict[str, Any]],
        table_name: str = "",
        client: "FakeSupabaseClient | None" = None,
    ) -> None:
        self._data = data
        self._table_name = table_name
        self._client = client

    def select(self, select_str: str = "*", count: Any = None) -> FakeQueryBuilder:
        return FakeQueryBuilder(
            self._data,
            "select",
            count_mode=(count is not None),
            select_str=select_str,
            table_name=self._table_name,
            client=self._client,
        )

    def insert(self, rows: list[dict[str, Any]] | dict[str, Any]) -> FakeQueryBuilder:
        return FakeQueryBuilder(
            self._data, "insert", payload=rows,
            table_name=self._table_name, client=self._client,
        )

    def update(self, data: dict[str, Any]) -> FakeQueryBuilder:
        return FakeQueryBuilder(
            self._data, "update", payload=data,
            table_name=self._table_name, client=self._client,
        )

    def delete(self) -> FakeQueryBuilder:
        return FakeQueryBuilder(
            self._data, "delete",
            table_name=self._table_name, client=self._client,
        )


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
        return FakeTable(self._tables[name], table_name=name, client=self)

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
