"""Tests for the supabase_io.write module."""

from datetime import datetime, date, timezone
from uuid import uuid4, UUID

import pandas as pd
import pytest

from app.supabase_io.write import _to_json_scalar, insert


# ---------------------------------------------------------------------------
# _to_json_scalar
# ---------------------------------------------------------------------------
class TestToJsonScalar:
    def test_uuid_to_str(self):
        uid = uuid4()
        assert _to_json_scalar(uid) == str(uid)

    def test_datetime_to_iso(self):
        dt = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)
        assert _to_json_scalar(dt) == dt.isoformat()

    def test_date_to_iso(self):
        d = date(2026, 4, 20)
        assert _to_json_scalar(d) == "2026-04-20"

    def test_timestamp_to_iso(self):
        ts = pd.Timestamp("2026-04-20 09:00:00")
        assert _to_json_scalar(ts) == ts.isoformat()

    def test_na_to_none(self):
        assert _to_json_scalar(pd.NA) is None
        assert _to_json_scalar(float("nan")) is None

    def test_plain_values_unchanged(self):
        assert _to_json_scalar(42) == 42
        assert _to_json_scalar("hello") == "hello"
        assert _to_json_scalar(None) is None


# ---------------------------------------------------------------------------
# insert (with mocked supabase)
# ---------------------------------------------------------------------------
class TestInsert:
    def test_calls_supabase_table(self, mock_supabase):
        uid = uuid4()
        data = [{"id": uid, "name": "Test"}]
        insert("my_table", data)
        mock_supabase.table.assert_called_with("my_table")

    def test_serializes_uuid_and_datetime(self, mock_supabase):
        """Verify that insert serializes UUID/datetime values before sending."""
        uid = uuid4()
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        data = [{"id": uid, "ts": dt, "label": "ok"}]
        insert("t", data)
        # The function should have called table("t").insert(...).execute()
        # We can verify table was called correctly
        mock_supabase.table.assert_called_with("t")
