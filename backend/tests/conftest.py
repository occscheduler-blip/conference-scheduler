import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest


# Make backend/app importable as top-level package "app".
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Ensure app imports can build a Supabase client during test module imports.
# Some CI environments may expose these vars as empty strings; treat empty as unset.
if not os.environ.get("SUPABASE_URL"):
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
if not os.environ.get("SUPABASE_KEY"):
    os.environ["SUPABASE_KEY"] = "test-key"
if not os.environ.get("BACKEND_API_KEY"):
    os.environ["BACKEND_API_KEY"] = "test-api-key"


@dataclass
class QueryRecorder:
    table: str
    actions: list[tuple[str, object]] = field(default_factory=list)
    response: object = field(default_factory=lambda: SimpleNamespace(data=[], count=0))

    def select(self, *args, **kwargs):
        self.actions.append(("select", {"args": args, "kwargs": kwargs}))
        return self

    def eq(self, field_name, value):
        self.actions.append(("eq", {"field": field_name, "value": value}))
        return self

    def in_(self, field_name, values):
        self.actions.append(("in_", {"field": field_name, "values": values}))
        return self

    def insert(self, payload):
        self.actions.append(("insert", payload))
        return self

    def delete(self):
        self.actions.append(("delete", None))
        return self

    def execute(self):
        self.actions.append(("execute", None))
        return self.response


class FakeSupabase:
    def __init__(self):
        self.queries: dict[str, QueryRecorder] = {}

    def table(self, name: str):
        if name not in self.queries:
            self.queries[name] = QueryRecorder(name)
        return self.queries[name]


@pytest.fixture
def fake_supabase():
    return FakeSupabase()
