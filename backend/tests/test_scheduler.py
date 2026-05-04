import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.scheduler.cp_sat import SolveSchedule
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
    result = SolveSchedule(problem)
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
    result = SolveSchedule(problem)
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
    result = SolveSchedule(problem)
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
    result = SolveSchedule(problem)
    assert result.status == "infeasible"
    assert "p1" in result.unscheduled_presentations


def test_buffer_enforced():
    """A presentation with a 3-minute buffer must leave a 3-minute gap before the next one in the same room."""
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
            PresentationInput(id="p1", title="Talk 1", duration_minutes=10, buffer_minutes=3),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=10, buffer_minutes=0),
        ),
        slot_minutes=1,
    )
    result = SolveSchedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2

    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")

    # Determine which is first in the single room
    first, second = (p1, p2) if p1.start < p2.start else (p2, p1)
    gap = (second.start - first.end).total_seconds() / 60

    if first.presentation_id == "p1":
        # p1 (buffer=3) is first — gap must be at least 3 minutes
        assert gap >= 3, f"Expected gap >= 3 min after buffered presentation, got {gap:.1f} min"
    else:
        # p2 (buffer=0) is first — no gap required from p2, p1 follows
        # p1's buffer doesn't apply to what comes after p1 in this case;
        # just confirm the schedule is valid (no overlap)
        assert gap >= 0


def test_same_class_same_room():
    """All presentations from the same class must be assigned to the same room."""
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
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30, class_id="class-A"),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30, class_id="class-A"),
            PresentationInput(id="p3", title="Talk 3", duration_minutes=30, class_id="class-B"),
        ),
    )
    result = SolveSchedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 3

    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")
    assert p1.room_index == p2.room_index, (
        f"p1 and p2 share class-A but were placed in different rooms: {p1.room_index} vs {p2.room_index}"
    )


def test_buffer_with_same_class_room():
    """Presentations from the same class with a buffer should be sequential in one room with the correct gap."""
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
            PresentationInput(id="p1", title="Talk 1", duration_minutes=10, buffer_minutes=3, class_id="class-A"),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=10, buffer_minutes=3, class_id="class-A"),
        ),
        slot_minutes=1,
    )
    result = SolveSchedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2

    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")

    assert p1.room_index == p2.room_index, "Same-class presentations must be in the same room"

    first, second = (p1, p2) if p1.start < p2.start else (p2, p1)
    gap = (second.start - first.end).total_seconds() / 60
    assert gap >= 3, f"Expected gap >= 3 min between buffered same-class presentations, got {gap:.1f} min"


def test_large_schedule_timing():
    """20 presentations across 4 rooms with varied professors should solve within 30 seconds."""
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
    result = SolveSchedule(problem, time_limit_seconds=10.0)
    elapsed = time.perf_counter() - start

    assert result.status in ("optimal", "feasible"), f"Scheduler returned: {result.status}, diagnostics: {result.diagnostics}"
    assert len(result.assignments) == 20
    assert elapsed < 30.0, f"Scheduler took too long: {elapsed:.2f}s"
    print(f"\nLarge schedule solved in {elapsed:.2f}s")

