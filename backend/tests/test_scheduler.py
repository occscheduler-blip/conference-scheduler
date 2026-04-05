import time
from datetime import datetime, timedelta, timezone

from app.scheduler.cp_sat import solve_schedule
from app.scheduler.models import AvailabilityWindow, PresentationInput, ScheduleProblem


def test_basic_schedule():
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=45),
        ),
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2


def test_no_double_booking():
    """A resource shared across two presentations should not be scheduled at the same time."""
    windows = (
        AvailabilityWindow(
            start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
        ),
    )
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=windows,
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30, resource_ids=("prof1",)),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30, resource_ids=("prof1",)),
        ),
        resource_windows={"prof1": windows},
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2
    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")
    assert not (p1.start < p2.end and p2.start < p1.end), "Shared resource was double-booked"


def test_room_capacity():
    """More presentations than rooms should still be scheduled sequentially."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30),
            PresentationInput(id="p3", title="Talk 3", duration_minutes=30),
        ),
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 3
    for a in result.assignments:
        assert a.room_index == 0


def test_infeasible_no_availability():
    """A presentation with no valid time slots should return infeasible."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=60),
        ),
    )
    result = solve_schedule(problem)
    assert result.status == "infeasible"
    assert "p1" in result.unscheduled_presentations


def test_large_schedule_timing():
    """20 presentations across 4 rooms with varied professors should solve within 10 seconds."""
    sym_windows = (
        AvailabilityWindow(
            start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
        ),
    )

    # 10 professors each available for the full day
    num_professors = 10
    resource_windows = {
        f"prof{i}": sym_windows for i in range(num_professors)
    }

    # 20 presentations, each assigned to one professor
    presentations = tuple(
        PresentationInput(
            id=f"p{i}",
            title=f"Talk {i}",
            duration_minutes=30,
            resource_ids=(f"prof{i % num_professors}",),
        )
        for i in range(20)
    )

    problem = ScheduleProblem(
        symposium_id="test-large",
        rooms_available=4,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows=resource_windows,
    )

    start = time.perf_counter()
    result = solve_schedule(problem, time_limit_seconds=10.0)
    elapsed = time.perf_counter() - start

    assert result.status in ("optimal", "feasible"), f"Scheduler returned: {result.status}, diagnostics: {result.diagnostics}"
    assert len(result.assignments) == 20
    assert elapsed < 10.0, f"Scheduler took too long: {elapsed:.2f}s"
    print(f"\nLarge schedule solved in {elapsed:.2f}s")
