import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest


# Make backend/app importable as top-level package "app".
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings

# Ensure app imports can build a Supabase client during test module imports.
# Force deterministic defaults so CI host env does not leak into tests.
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_KEY"] = "test-key"
os.environ["BACKEND_API_KEY"] = "test-api-key"


@pytest.fixture(autouse=True)
def stable_test_environment(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("BACKEND_API_KEY", "test-api-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
