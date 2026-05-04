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

    def test_avoids_double_booking_student_across_presentations(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=2,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="Department A Thesis",
                    duration_minutes=30,
                    resource_ids=("student-shared",),
                ),
                PresentationInput(
                    id="p2",
                    title="Department B Thesis",
                    duration_minutes=30,
                    resource_ids=("student-shared",),
                ),
            ),
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        assert len(result.assignments) == 2
        starts = sorted(assignment.start for assignment in result.assignments)
        assert starts == [_dt(9), _dt(9, 30)]

    def test_marks_presentation_unschedulable_when_professor_availability_blocks_it(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="Blocked",
                    duration_minutes=30,
                    resource_ids=("prof-a",),
                ),
            ),
            resource_windows={
                "prof-a": (AvailabilityWindow(start=_dt(9), end=_dt(9, 15)),)
            },
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status == "infeasible"
        assert result.unscheduled_presentations == ("p1",)
        assert result.assignments == ()
        assert "no valid start times" in result.diagnostics[0].lower()
        assert len(result.suggestions) == 3

    def test_suggests_adding_time_when_total_capacity_is_too_small(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(id="p1", title="One", duration_minutes=30),
                PresentationInput(id="p2", title="Two", duration_minutes=30),
                PresentationInput(id="p3", title="Three", duration_minutes=30),
            ),
            slot_minutes=30,
        )

        result = solve_schedule(problem)

        assert result.status == "infeasible"
        assert result.assignments == ()
        assert result.unscheduled_presentations == ("p1", "p2", "p3")
        assert len(result.suggestions) == 3
        assert any("add more symposium time" in suggestion.lower() for suggestion in result.suggestions)

    def test_student_declared_availability_is_soft(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="Student Preferred Away",
                    duration_minutes=30,
                    resource_ids=("student-a",),
                ),
            ),
            soft_resource_windows={
                "student-a": (AvailabilityWindow(start=_dt(9), end=_dt(9, 15)),)
            },
            slot_minutes=5,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        assert len(result.assignments) == 1

    def test_student_declared_availability_is_preferred_when_feasible(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="Student Preferred Inside",
                    duration_minutes=30,
                    resource_ids=("student-a",),
                ),
                PresentationInput(id="p2", title="Other", duration_minutes=30),
            ),
            soft_resource_windows={
                "student-a": (AvailabilityWindow(start=_dt(9, 30), end=_dt(10)),)
            },
            slot_minutes=30,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        assignment_by_id = {
            assignment.presentation_id: assignment for assignment in result.assignments
        }
        assert assignment_by_id["p1"].start == _dt(9, 30)

    def test_feasible_schedule_has_no_admin_suggestions(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(id="p1", title="One", duration_minutes=30),
                PresentationInput(id="p2", title="Two", duration_minutes=30),
            ),
            slot_minutes=30,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        assert result.suggestions == ()

    def test_prefers_same_class_presentations_adjacent_in_time(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=1,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(11)),),
            presentations=(
                PresentationInput(
                    id="a1",
                    title="Class A One",
                    duration_minutes=30,
                    class_id="class-a",
                ),
                PresentationInput(
                    id="a2",
                    title="Class A Two",
                    duration_minutes=30,
                    class_id="class-a",
                ),
                PresentationInput(id="b1", title="Class B", duration_minutes=30),
                PresentationInput(id="c1", title="Class C", duration_minutes=30),
            ),
            slot_minutes=30,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        starts = {
            assignment.presentation_id: assignment.start for assignment in result.assignments
        }
        assert abs((starts["a2"] - starts["a1"]).total_seconds()) == 30 * 60

    def test_prefers_back_to_back_professor_presentations(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=2,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10, 30)),),
            presentations=(
                PresentationInput(
                    id="p1",
                    title="Prof One",
                    duration_minutes=30,
                    resource_ids=("prof-a",),
                ),
                PresentationInput(
                    id="p2",
                    title="Prof Two",
                    duration_minutes=30,
                    resource_ids=("prof-a",),
                ),
                PresentationInput(id="x1", title="Other One", duration_minutes=30),
                PresentationInput(id="x2", title="Other Two", duration_minutes=30),
                PresentationInput(id="x3", title="Other Three", duration_minutes=30),
                PresentationInput(id="x4", title="Other Four", duration_minutes=30),
            ),
            professor_resource_ids=("prof-a",),
            resource_windows={
                "prof-a": (AvailabilityWindow(start=_dt(9), end=_dt(10, 30)),)
            },
            slot_minutes=30,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        starts = {
            assignment.presentation_id: assignment.start for assignment in result.assignments
        }
        assert abs((starts["p2"] - starts["p1"]).total_seconds()) == 30 * 60

    def test_prefers_balanced_room_usage_when_makespan_ties(self):
        problem = ScheduleProblem(
            symposium_id="sym-1",
            rooms_available=3,
            symposium_windows=(AvailabilityWindow(start=_dt(9), end=_dt(10)),),
            presentations=(
                PresentationInput(id="p1", title="One", duration_minutes=30),
                PresentationInput(id="p2", title="Two", duration_minutes=30),
                PresentationInput(id="p3", title="Three", duration_minutes=30),
                PresentationInput(id="p4", title="Four", duration_minutes=30),
            ),
            slot_minutes=30,
        )

        result = solve_schedule(problem)

        assert result.status in {"optimal", "feasible"}
        room_counts: dict[int, int] = {}
        for assignment in result.assignments:
            room_counts[assignment.room_index] = room_counts.get(assignment.room_index, 0) + 1

        assert len(room_counts) == 3
        assert max(room_counts.values()) - min(room_counts.values()) <= 1
