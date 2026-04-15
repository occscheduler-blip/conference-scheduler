from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from app.scheduler.models import AvailabilityWindow, ScheduleProblem, ScheduleResult, ScheduledPresentation
from app.scheduler.service import _assignments_within_symposium_windows, _save_assignments

# Force `delete` and `write` to be imported as attributes of the namespace
# package before the test runs, so monkeypatching them works when this file
# is run in isolation.
from app.supabase_io import delete as _delete, write as _write  # noqa: F401


def test_save_assignments_clears_unscheduled_presentations(monkeypatch):
    deleted_ids: list[str] = []
    inserted_rows: list[dict[str, object]] = []
    update_calls: list[tuple[str, str, dict[UUID, object]]] = []

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

        @staticmethod
        def update_column_by_ids(
            table_name: str,
            column: str,
            id_to_value: Mapping[UUID, object],
        ) -> int:
            update_calls.append((table_name, column, dict(id_to_value)))
            return len(id_to_value)

    import app.supabase_io

    monkeypatch.setattr(app.supabase_io, "delete", _FakeDelete)
    monkeypatch.setattr(app.supabase_io, "write", _FakeWrite)

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
    # First call clears rooms to None for every presentation in the symposium;
    # second call sets the scheduled ones to their assigned room index.
    assert update_calls == [
        (
            "presentations",
            "room",
            {
                UUID("00000000-0000-0000-0000-000000000001"): None,
                UUID("00000000-0000-0000-0000-000000000002"): None,
            },
        ),
        (
            "presentations",
            "room",
            {UUID("00000000-0000-0000-0000-000000000001"): 1},
        ),
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
