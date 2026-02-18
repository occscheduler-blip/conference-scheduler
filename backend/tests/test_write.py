from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd

from app.supabase_io import write


def test_to_json_scalar_handles_uuid_datetime_and_nan():
    value_uuid = uuid4()
    value_time = datetime(2026, 4, 20, 9, 30, tzinfo=timezone.utc)

    assert write._to_json_scalar(value_uuid) == str(value_uuid)
    assert write._to_json_scalar(value_time) == value_time.isoformat()
    assert write._to_json_scalar(pd.NA) is None
    assert write._to_json_scalar("plain") == "plain"


def test_insert_serializes_values_and_executes_query(fake_supabase, monkeypatch):
    response = SimpleNamespace(data=[{"ok": True}], count=1)
    fake_supabase.table("students").response = response
    monkeypatch.setattr(write, "supabase", fake_supabase)

    student_id = uuid4()
    created = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    result = write.insert(
        "students",
        [{"id": student_id, "created_at": created, "nickname": pd.NA}],
    )

    assert result is response
    actions = fake_supabase.queries["students"].actions
    insert_payload = next(payload for name, payload in actions if name == "insert")
    assert insert_payload[0]["id"] == str(student_id)
    assert insert_payload[0]["created_at"] == created.isoformat()
    assert insert_payload[0]["nickname"] is None
