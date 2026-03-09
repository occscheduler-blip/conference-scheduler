"""Shared fixtures for backend tests.

Mocks the Supabase client so tests run without a live database.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# Set required env vars BEFORE any app module is imported.
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("BACKEND_API_KEY", "test-api-key")


def _make_response(data=None, count=None):
    """Build a lightweight object that looks like a Supabase response."""
    return SimpleNamespace(data=data or [], count=count)


@pytest.fixture()
def mock_supabase():
    """Patch the global supabase client used by the I/O layer."""
    fake_client = MagicMock(name="supabase_client")

    def _table(name):
        table_mock = MagicMock(name=f"table:{name}")
        # Default chaining returns an empty response
        for method in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
            getattr(table_mock, method).return_value = table_mock
        table_mock.execute.return_value = _make_response()
        return table_mock

    fake_client.table.side_effect = _table

    with patch("app.supabase_io.client.supabase", fake_client), \
         patch("app.supabase_io.read.supabase", fake_client), \
         patch("app.supabase_io.write.supabase", fake_client), \
         patch("app.supabase_io.delete.supabase", fake_client), \
         patch("app.supabase_io.nested_read.supabase", fake_client), \
         patch("app.routers.events.supabase", fake_client):
        yield fake_client


@pytest.fixture()
def api_headers():
    """Return headers dict with a valid API key."""
    return {"X-API-Key": "test-api-key"}


@pytest.fixture()
def client(mock_supabase):
    """FastAPI TestClient with Supabase mocked out."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def fake_supabase():
    """Fully in-memory Supabase client — real data flows through supabase_io."""
    from tests.fake_supabase import FakeSupabaseClient
    db = FakeSupabaseClient()
    with patch("app.supabase_io.client.supabase", db), \
         patch("app.supabase_io.read.supabase", db), \
         patch("app.supabase_io.write.supabase", db), \
         patch("app.supabase_io.delete.supabase", db), \
         patch("app.supabase_io.nested_read.supabase", db), \
         patch("app.routers.events.supabase", db):
        yield db


@pytest.fixture()
def integration_client(fake_supabase):
    """FastAPI TestClient backed by the in-memory Supabase."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Reusable UUID constants
# ---------------------------------------------------------------------------
SYMPOSIUM_ID = uuid4()
DEPARTMENT_ID = uuid4()
CLASS_ID = uuid4()
PROFESSOR_ID = uuid4()
STUDENT_ID = uuid4()
PRESENTATION_ID = uuid4()
TIMEFRAME_ID = uuid4()
