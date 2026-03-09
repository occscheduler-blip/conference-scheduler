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
        mock_supabase.table.assert_called_with("t")

    def test_no_raw_uuids_or_datetimes_sent_to_supabase(self, mock_supabase):
        """
        The rows passed to supabase.insert() must contain only JSON-safe scalars.
        Any UUID or datetime object left unconverted would cause a runtime error
        when Supabase serializes the request.
        """
        # Capture the table mock returned by the side_effect (table.return_value is bypassed)
        captured: dict[str, object] = {}
        original_se = mock_supabase.table.side_effect

        def _capturing(name: str) -> object:
            table = original_se(name)
            captured[name] = table
            return table

        mock_supabase.table.side_effect = _capturing

        uid = uuid4()
        dt = datetime(2026, 4, 20, 9, 0, 0, tzinfo=timezone.utc)
        d = date(2026, 4, 20)
        ts = pd.Timestamp("2026-04-20 09:00:00")
        data = [{"id": uid, "created_at": dt, "day": d, "ts": ts, "label": "ok", "count": 5, "empty": None}]
        insert("t", data)

        # Retrieve the actual table mock used during insert
        assert "t" in captured, "insert() never called supabase.table('t')"
        insert_call = captured["t"].insert  # type: ignore[union-attr]
        assert insert_call.called
        sent_rows = insert_call.call_args[0][0]
        assert len(sent_rows) == 1
        row = sent_rows[0]

        for key, val in row.items():
            assert not isinstance(val, UUID), f"Field '{key}' is still a UUID object"
            assert not isinstance(val, (datetime, date, pd.Timestamp)), (
                f"Field '{key}' is still a datetime/date/Timestamp object"
            )
        # Spot-check expected converted values
        assert row["id"] == str(uid)
        assert row["created_at"] == dt.isoformat()
        assert row["day"] == "2026-04-20"
        assert row["ts"] == ts.isoformat()
        assert row["label"] == "ok"
        assert row["count"] == 5
        assert row["empty"] is None
