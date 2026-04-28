from __future__ import annotations

from datetime import datetime, timezone

from app.scheduler.models import AvailabilityWindow, ScheduleProblem, ScheduleResult, ScheduledPresentation
from app.scheduler.service import _assignments_within_symposium_windows, _save_assignments



def test_save_assignments_clears_unscheduled_presentations(monkeypatch):
    deleted_ids: list[str] = []
    inserted_rows: list[dict[str, object]] = []

    import app.supabase_io.delete as _delete_mod
    import app.supabase_io.write as _write_mod

    monkeypatch.setattr(_delete_mod, "delete_temporary_timeframes", lambda ids: deleted_ids.extend(str(v) for v in ids))
    monkeypatch.setattr(_write_mod, "insert", lambda table, rows: inserted_rows.extend(rows))
    monkeypatch.setattr(_write_mod, "update_column_by_ids", lambda table, col, mapping: None)

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
        symposium_id="00000000-0000-0000-0000-000000000099",
    )

    assert set(deleted_ids) == {
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    }
    assert len(inserted_rows) == 1
    assert str(inserted_rows[0]["linked_id"]) == "00000000-0000-0000-0000-000000000001"


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
