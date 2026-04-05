from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil

from ortools.sat.python import cp_model

from .models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduledPresentation,
    ScheduleProblem,
    ScheduleResult,
)


def _ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _normalize_windows(
    windows: tuple[AvailabilityWindow, ...],
) -> tuple[AvailabilityWindow, ...]:
    normalized = tuple(
        sorted(
            (
                AvailabilityWindow(
                    start=_ensure_utc(window.start), end=_ensure_utc(window.end)
                )
                for window in windows
                if window.end > window.start
            ),
            key=lambda window: window.start,
        )
    )
    return normalized


def _window_contains(
    windows: tuple[AvailabilityWindow, ...], start: datetime, end: datetime
) -> bool:
    return any(start >= window.start and end <= window.end for window in windows)


def _slot_count(duration_minutes: int, slot_minutes: int) -> int:
    return ceil(duration_minutes / slot_minutes)


def _eligible_starts(
    presentation: PresentationInput,
    symposium_windows: tuple[AvailabilityWindow, ...],
    resource_windows: dict[str, tuple[AvailabilityWindow, ...]],
    slot_minutes: int,
) -> tuple[datetime, ...]:
    starts: list[datetime] = []
    duration = timedelta(minutes=presentation.duration_minutes)
    step = timedelta(minutes=slot_minutes)

    for window in symposium_windows:
        candidate = window.start
        while candidate + duration <= window.end:
            end = candidate + duration
            if all(
                _window_contains(resource_windows[resource_id], candidate, end)
                for resource_id in presentation.resource_ids
                if resource_id in resource_windows
            ):
                starts.append(candidate)
            candidate += step

    return tuple(starts)


def solve_schedule(
    problem: ScheduleProblem, time_limit_seconds: float = 10.0
) -> ScheduleResult:
    if problem.rooms_available < 1:
        return ScheduleResult(
            status="invalid",
            assignments=(),
            diagnostics=("rooms_available must be at least 1",),
        )

    if problem.slot_minutes < 1:
        return ScheduleResult(
            status="invalid",
            assignments=(),
            diagnostics=("slot_minutes must be at least 1",),
        )

    symposium_windows = _normalize_windows(problem.symposium_windows)
    if not symposium_windows:
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=("No symposium availability windows were provided.",),
        )

    if not problem.presentations:
        return ScheduleResult(
            status="optimal",
            assignments=(),
            diagnostics=("No presentations were provided.",),
        )

    resource_windows = {
        resource_id: _normalize_windows(windows)
        for resource_id, windows in problem.resource_windows.items()
    }

    eligible_starts: dict[str, tuple[datetime, ...]] = {}
    unschedulable: list[str] = []
    diagnostics: list[str] = []

    for presentation in problem.presentations:
        if presentation.duration_minutes < 1:
            return ScheduleResult(
                status="invalid",
                assignments=(),
                diagnostics=(
                    f"Presentation {presentation.id} has an invalid duration.",
                ),
            )
        starts = _eligible_starts(
            presentation=presentation,
            symposium_windows=symposium_windows,
            resource_windows=resource_windows,
            slot_minutes=problem.slot_minutes,
        )
        eligible_starts[presentation.id] = starts
        if not starts:
            unschedulable.append(presentation.id)
            diagnostics.append(
                f"Presentation {presentation.id} has no valid start times after availability filtering."
            )

    if unschedulable:
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(unschedulable),
            diagnostics=tuple(diagnostics),
        )

    model = cp_model.CpModel()
    assignment_vars: dict[tuple[str, int, int], cp_model.IntVar] = {}
    start_index_vars: dict[str, cp_model.IntVar] = {}
    end_index_vars: dict[str, cp_model.IntVar] = {}
    option_lookup: dict[tuple[str, int, int], tuple[datetime, datetime]] = {}
    all_instants: set[datetime] = set()
    step = timedelta(minutes=problem.slot_minutes)

    base_time = min(window.start for window in symposium_windows)

    for presentation in problem.presentations:
        option_indices: list[int] = []
        durations_slots = _slot_count(
            presentation.duration_minutes, problem.slot_minutes
        )
        for option_index, start_time in enumerate(eligible_starts[presentation.id]):
            end_time = start_time + timedelta(minutes=presentation.duration_minutes)
            all_instants.add(start_time)
            all_instants.add(end_time)
            start_slot = int((start_time - base_time) / step)
            option_indices.append(start_slot)
            for room_index in range(problem.rooms_available):
                var = model.NewBoolVar(
                    f"assign_{presentation.id}_{option_index}_{room_index}"
                )
                assignment_vars[(presentation.id, option_index, room_index)] = var
                option_lookup[(presentation.id, option_index, room_index)] = (
                    start_time,
                    end_time,
                )
        "Each presentation must be assigned exactly once"
        model.Add(
            sum(
                assignment_vars[(presentation.id, option_index, room_index)]
                for option_index in range(len(eligible_starts[presentation.id]))
                for room_index in range(problem.rooms_available)
            )
            == 1
        )

        start_index = model.NewIntVar(
            min(option_indices),
            max(option_indices),
            f"start_slot_{presentation.id}",
        )
        end_index = model.NewIntVar(
            min(option_indices) + durations_slots,
            max(option_indices) + durations_slots,
            f"end_slot_{presentation.id}",
        )
        start_index_vars[presentation.id] = start_index
        end_index_vars[presentation.id] = end_index
        "chosen start slot must match the selected assignment option"
        model.Add(
            start_index
            == sum(
                int((eligible_starts[presentation.id][option_index] - base_time) / step)
                * assignment_vars[(presentation.id, option_index, room_index)]
                for option_index in range(len(eligible_starts[presentation.id]))
                for room_index in range(problem.rooms_available)
            )
        )
        model.Add(end_index == start_index + durations_slots)

    all_instants = {
        instant
        for instant in all_instants
        if any(
            instant >= window.start and instant < window.end
            for window in symposium_windows
        )
    }

    for instant in sorted(all_instants):
        for room_index in range(problem.rooms_available):
            overlapping = []
            for presentation in problem.presentations:
                for option_index in range(len(eligible_starts[presentation.id])):
                    key = (presentation.id, option_index, room_index)
                    start_time, end_time = option_lookup[key]
                    # extend end by buffer so next presentation can't start during buffer
                    buffered_end = end_time + timedelta(minutes=presentation.buffer_minutes)
                    if start_time <= instant < buffered_end:
                        overlapping.append(assignment_vars[key])
            if overlapping:
                "no two presentations can overlap in the same room"
                model.Add(sum(overlapping) <= 1)

        resources_at_time: dict[str, list[cp_model.IntVar]] = defaultdict(list)
        for presentation in problem.presentations:
            for resource_id in presentation.resource_ids:
                for option_index in range(len(eligible_starts[presentation.id])):
                    for room_index in range(problem.rooms_available):
                        key = (presentation.id, option_index, room_index)
                        start_time, end_time = option_lookup[key]
                        if start_time <= instant < end_time:
                            resources_at_time[resource_id].append(assignment_vars[key])

        for overlapping in resources_at_time.values():
            if overlapping:
                "nothing can be double-booked, ex 2 presentations at the same time for one prof"
                model.Add(sum(overlapping) <= 1)

    makespan = model.NewIntVar(0, 1000000, "makespan")
    "soft contraint: try ti minimize the overall finishing time of symposium"
    model.AddMaxEquality(makespan, list(end_index_vars.values()))
    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=("CP-SAT could not find a feasible schedule.",),
        )

    assignments: list[ScheduledPresentation] = []
    for presentation in problem.presentations:
        for option_index in range(len(eligible_starts[presentation.id])):
            for room_index in range(problem.rooms_available):
                key = (presentation.id, option_index, room_index)
                if solver.Value(assignment_vars[key]) == 1:
                    start_time, end_time = option_lookup[key]
                    assignments.append(
                        ScheduledPresentation(
                            presentation_id=presentation.id,
                            room_index=room_index,
                            start=start_time,
                            end=end_time,
                        )
                    )

    assignments.sort(
        key=lambda item: (item.start, item.room_index, item.presentation_id)
    )
    result_status = "optimal" if status == cp_model.OPTIMAL else "feasible"
    return ScheduleResult(
        status=result_status,
        assignments=tuple(assignments),
        diagnostics=tuple(diagnostics),
    )