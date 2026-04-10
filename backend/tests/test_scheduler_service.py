from __future__ import annotations

from datetime import datetime, timezone

from app.scheduler.models import AvailabilityWindow, ScheduleProblem, ScheduleResult, ScheduledPresentation
from app.scheduler.service import _assignments_within_symposium_windows, _save_assignments


class _FakeExecute:
    def execute(self):
        return self


class _FakeUpdate(_FakeExecute):
    def __init__(self, updates: list[tuple[dict[str, int | None], str]]):
        self._updates = updates
        self._payload: dict[str, int | None] | None = None

    def eq(self, field: str, value: str):
        assert field == "id"
        assert self._payload is not None
        self._updates.append((self._payload, value))
        return self


class _FakeTable:
    def __init__(self, updates: list[tuple[dict[str, int | None], str]]):
        self._updates = updates

    def update(self, payload: dict[str, int | None]):
        updater = _FakeUpdate(self._updates)
        updater._payload = payload
        return updater


class _FakeSupabase:
    def __init__(self):
        self.updates: list[tuple[dict[str, int | None], str]] = []

    def table(self, name: str):
        assert name == "presentations"
        return _FakeTable(self.updates)


def test_save_assignments_clears_unscheduled_presentations(monkeypatch):
    deleted_ids: list[str] = []
    inserted_rows: list[dict[str, object]] = []
    fake_supabase = _FakeSupabase()

    class _FakeDelete:
        @staticmethod
        def delete_timeframes(linked_id):
            deleted_ids.extend(str(value) for value in linked_id)
            return len(linked_id)

    class _FakeWrite:
        @staticmethod
        def insert(table_name: str, rows: list[dict[str, object]]):
            assert table_name == "timeframes"
            inserted_rows.extend(rows)

    monkeypatch.setattr("app.scheduler.service.supabase", fake_supabase)
    monkeypatch.setitem(__import__("sys").modules, "app.supabase_io.delete", _FakeDelete)
    monkeypatch.setitem(__import__("sys").modules, "app.supabase_io.write", _FakeWrite)

    result = ScheduleResult(
        status="feasible",
        assignments=(
            ScheduledPresentation(
                presentation_id="00000000-0000-0000-0000-000000000001",
                room_index=1,
                start=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
                end=datetime(2026, 4, 20, 9, 30, tzinfo=timezone.utc),
            ),
        ),
        unscheduled_presentations=("00000000-0000-0000-0000-000000000002",),
    )

    _save_assignments(
        result,
        (
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ),
    )

    assert deleted_ids == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ]
    assert fake_supabase.updates == [
        ({"room": None}, "00000000-0000-0000-0000-000000000001"),
        ({"room": None}, "00000000-0000-0000-0000-000000000002"),
        ({"room": 1}, "00000000-0000-0000-0000-000000000001"),
    ]
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["linked_id"].hex == "00000000000000000000000000000001"


def test_assignment_guard_rejects_out_of_window_result():
    problem = ScheduleProblem(
        symposium_id="sym-1",
        rooms_available=1,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
                end=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(),
    )
    result = ScheduleResult(
        status="feasible",
        assignments=(
            ScheduledPresentation(
                presentation_id="p1",
                room_index=0,
                start=datetime(2026, 4, 20, 17, 15, tzinfo=timezone.utc),
                end=datetime(2026, 4, 20, 17, 45, tzinfo=timezone.utc),
            ),
        ),
    )

    assert not _assignments_within_symposium_windows(problem, result)
