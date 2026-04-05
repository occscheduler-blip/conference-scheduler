from datetime import datetime, timezone

from app.scheduler import (
    AvailabilityWindow,
    PresentationInput,
    ScheduleProblem,
    solve_schedule,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 20, hour, minute, tzinfo=timezone.utc)


class TestCPSATScheduler:
    def test_empty_problem_returns_empty_schedule(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(),
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status == "optimal"
        assert result.assignments == ()

    def test_schedules_two_presentations_in_parallel_when_rooms_allow(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=2,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(id="p1", title="One", duration_minutes=30),
                PresentationInput(id="p2", title="Two", duration_minutes=30),
            ),
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        assert len(result.assignments) == 2
        assert {assignment.start for assignment in result.assignments} == {_dt(9)}
        assert {assignment.room_index for assignment in result.assignments} == {0, 1}

    def test_avoids_double_booking_shared_resource(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=2,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="One",
                    duration_minutes=30,
                    resource_ids=("prof-a",),
                ),
                PresentationInput(
                    id="p2",
                    title="Two",
                    duration_minutes=30,
                    resource_ids=("prof-a",),
                ),
            ),
            resource_windows={"prof-a": (AvailabilityWindow(start=_dt(9), end=_dt(10)),)},
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        assert len(result.assignments) == 2
        starts = sorted(assignment.start for assignment in result.assignments)
        assert starts == [_dt(9), _dt(9, 30)]

    def test_marks_presentation_unschedulable_when_resource_availability_blocks_it(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="Blocked",
                    duration_minutes=30,
                    resource_ids=("student-a",),
                ),
            ),
            resource_windows={
                "student-a": (AvailabilityWindow(start=_dt(9), end=_dt(9, 15)),)
            },
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status == "infeasible"
        assert result.unscheduled_presentations == ("p1",)
        assert "no valid start times" in result.diagnostics[0].lower()
