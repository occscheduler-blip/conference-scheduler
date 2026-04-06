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


def _objective_weighted_sum(
    makespan: cp_model.IntVar,
    soft_availability_terms: list[cp_model.IntVar],
    class_span_terms: list[cp_model.IntVar],
    professor_span_terms: list[cp_model.IntVar],
    room_imbalance_terms: list[cp_model.IntVar],
    horizon_slots: int,
) -> cp_model.LinearExpr:
    max_room_imbalance = max(len(room_imbalance_terms), 1) * horizon_slots
    max_professor_span = max(len(professor_span_terms), 1) * horizon_slots
    max_class_span = max(len(class_span_terms), 1) * horizon_slots
    max_soft_availability = max(len(soft_availability_terms), 1) * len(
        soft_availability_terms or [0]
    )

    room_weight = 1
    professor_weight = max_room_imbalance + 1
    class_weight = max_professor_span * professor_weight + max_room_imbalance + 1
    soft_availability_weight = (
        max_class_span * class_weight
        + max_professor_span * professor_weight
        + max_room_imbalance
        + 1
    )
    makespan_weight = (
        max_soft_availability * soft_availability_weight
        + max_class_span * class_weight
        + max_professor_span * professor_weight
        + max_room_imbalance
        + 1
    )

    return (
        makespan * makespan_weight
        + sum(soft_availability_terms) * soft_availability_weight
        + sum(class_span_terms) * class_weight
        + sum(professor_span_terms) * professor_weight
        + sum(room_imbalance_terms) * room_weight
    )


def _build_admin_suggestions(
    problem: ScheduleProblem,
    diagnostics: tuple[str, ...],
    unscheduled_presentations: tuple[str, ...],
) -> tuple[str, ...]:
    suggestions: list[str] = []
    total_room_minutes = (
        sum(
            int((window.end - window.start).total_seconds() // 60)
            for window in problem.symposium_windows
        )
        * problem.rooms_available
    )
    total_required_minutes = sum(
        presentation.duration_minutes + presentation.buffer_minutes
        for presentation in problem.presentations
    )

    blocked_by_professor = any(
        "no valid start times" in message.lower()
        for message in diagnostics
    ) and bool(problem.professor_resource_ids)
    if blocked_by_professor:
        suggestions.append(
            "Review professor availability windows for the blocked presentations or widen those windows in the admin settings."
        )

    class_ids = {presentation.class_id for presentation in problem.presentations if presentation.class_id}
    if class_ids:
        suggestions.append(
            "Change the 'same class must stay in the same room' rule from hard to soft if you want the solver to use more rooms."
        )

    if any(presentation.buffer_minutes > 0 for presentation in problem.presentations):
        suggestions.append(
            "Reduce the required room buffer between presentations, or make that rule softer, to free more scheduling options."
        )

    if problem.soft_resource_windows:
        suggestions.append(
            "Keep student availability as a soft preference, but consider lowering its weight if student preferences are crowding the schedule."
        )

    if total_required_minutes > total_room_minutes:
        suggestions.append(
            "There is not enough total room time to place every presentation. Add more symposium time or increase the number of rooms."
        )
    else:
        suggestions.append(
            "Increase room count or expand symposium timeframes if you want to preserve the current hard constraints."
        )

    if unscheduled_presentations:
        suggestions.append(
            "Open the blocked presentations in the admin editor and relax one hard rule at a time, then rerun the scheduler to see which rule is causing infeasibility."
        )

    fallback_suggestions = (
        "Review the hard-vs-soft settings for room usage, class grouping, and availability, then rerun the scheduler.",
        "Inspect the unscheduled presentations first and compare their durations, buffers, and attached people against the available windows.",
        "Keep 'all presentations must be scheduled' as a hard rule, and adjust time, rooms, or editable constraint settings around it.",
    )
    for suggestion in fallback_suggestions:
        if len(suggestions) >= 3:
            break
        if suggestion not in suggestions:
            suggestions.append(suggestion)

    return tuple(suggestions[:3])


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
            suggestions=(
                "Add at least one symposium timeframe before running the scheduler.",
                "Increase the symposium date range if presentations need more placement options.",
                "Review the scheduling settings and rerun after adding availability.",
            ),
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
    soft_resource_windows = {
        resource_id: _normalize_windows(windows)
        for resource_id, windows in problem.soft_resource_windows.items()
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
        suggestions = _build_admin_suggestions(
            problem=problem,
            diagnostics=tuple(diagnostics),
            unscheduled_presentations=tuple(unschedulable),
        )
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(unschedulable),
            diagnostics=tuple(diagnostics),
            suggestions=suggestions,
        )

    model = cp_model.CpModel()
    assignment_vars: dict[tuple[str, int, int], cp_model.IntVar] = {}
    start_index_vars: dict[str, cp_model.IntVar] = {}
    end_index_vars: dict[str, cp_model.IntVar] = {}
    option_lookup: dict[tuple[str, int, int], tuple[datetime, datetime]] = {}
    soft_penalty_lookup: dict[tuple[str, int], int] = {}
    all_instants: set[datetime] = set()
    step = timedelta(minutes=problem.slot_minutes)

    base_time = min(window.start for window in symposium_windows)
    horizon_slots = max(
        int((window.end - base_time) / step) for window in symposium_windows
    )

    for presentation in problem.presentations:
        option_indices: list[int] = []
        durations_slots = _slot_count(
            presentation.duration_minutes, problem.slot_minutes
        )
        for option_index, start_time in enumerate(eligible_starts[presentation.id]):
            end_time = start_time + timedelta(minutes=presentation.duration_minutes)
            buffered_end = end_time + timedelta(minutes=presentation.buffer_minutes)
            all_instants.add(start_time)
            all_instants.add(end_time)
            all_instants.add(buffered_end)
            start_slot = int((start_time - base_time) / step)
            option_indices.append(start_slot)
            soft_penalty_lookup[(presentation.id, option_index)] = sum(
                1
                for resource_id in presentation.resource_ids
                if resource_id in soft_resource_windows
                and not _window_contains(
                    soft_resource_windows[resource_id], start_time, end_time
                )
            )
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

    # Group presentations by class and enforce same-room constraint.
    presentations_by_class: dict[str, list[PresentationInput]] = defaultdict(list)
    presentations_by_resource: dict[str, list[PresentationInput]] = defaultdict(list)
    for presentation in problem.presentations:
        if presentation.class_id:
            presentations_by_class[presentation.class_id].append(presentation)
        for resource_id in presentation.resource_ids:
            presentations_by_resource[resource_id].append(presentation)

    for class_id, class_presentations in presentations_by_class.items():
        if len(class_presentations) < 2:
            continue
        class_room_var = model.NewIntVar(
            0, problem.rooms_available - 1, f"class_room_{class_id}"
        )
        for presentation in class_presentations:
            for option_index in range(len(eligible_starts[presentation.id])):
                for room_index in range(problem.rooms_available):
                    key = (presentation.id, option_index, room_index)
                    model.Add(class_room_var == room_index).OnlyEnforceIf(
                        assignment_vars[key]
                    )

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
    model.AddMaxEquality(makespan, list(end_index_vars.values()))

    soft_availability_terms: list[cp_model.IntVar] = []
    total_soft_penalty = model.NewIntVar(
        0, len(problem.presentations) * max(len(soft_resource_windows), 1), "soft_availability_penalty"
    )
    model.Add(
        total_soft_penalty
        == sum(
            soft_penalty_lookup[(presentation.id, option_index)]
            * assignment_vars[(presentation.id, option_index, room_index)]
            for presentation in problem.presentations
            for option_index in range(len(eligible_starts[presentation.id]))
            for room_index in range(problem.rooms_available)
        )
    )
    soft_availability_terms.append(total_soft_penalty)

    class_span_terms: list[cp_model.IntVar] = []
    for class_id, class_presentations in presentations_by_class.items():
        if len(class_presentations) < 2:
            continue
        class_start = model.NewIntVar(0, horizon_slots, f"class_start_{class_id}")
        class_end = model.NewIntVar(0, horizon_slots, f"class_end_{class_id}")
        class_span = model.NewIntVar(0, horizon_slots, f"class_span_{class_id}")
        model.AddMinEquality(
            class_start,
            [start_index_vars[presentation.id] for presentation in class_presentations],
        )
        model.AddMaxEquality(
            class_end,
            [end_index_vars[presentation.id] for presentation in class_presentations],
        )
        model.Add(class_span == class_end - class_start)
        class_span_terms.append(class_span)

    professor_span_terms: list[cp_model.IntVar] = []
    for resource_id in problem.professor_resource_ids:
        resource_presentations = presentations_by_resource.get(resource_id, [])
        if len(resource_presentations) < 2:
            continue
        professor_start = model.NewIntVar(
            0, horizon_slots, f"professor_start_{resource_id}"
        )
        professor_end = model.NewIntVar(
            0, horizon_slots, f"professor_end_{resource_id}"
        )
        professor_span = model.NewIntVar(
            0, horizon_slots, f"professor_span_{resource_id}"
        )
        model.AddMinEquality(
            professor_start,
            [start_index_vars[presentation.id] for presentation in resource_presentations],
        )
        model.AddMaxEquality(
            professor_end,
            [end_index_vars[presentation.id] for presentation in resource_presentations],
        )
        model.Add(professor_span == professor_end - professor_start)
        professor_span_terms.append(professor_span)

    room_load_terms: list[cp_model.IntVar] = []
    room_imbalance_terms: list[cp_model.IntVar] = []
    if problem.rooms_available > 1:
        for room_index in range(problem.rooms_available):
            room_load = model.NewIntVar(
                0, len(problem.presentations), f"room_load_{room_index}"
            )
            model.Add(
                room_load
                == sum(
                    assignment_vars[(presentation.id, option_index, room_index)]
                    for presentation in problem.presentations
                    for option_index in range(len(eligible_starts[presentation.id]))
                )
            )
            room_load_terms.append(room_load)

        max_room_load = model.NewIntVar(
            0, len(problem.presentations), "max_room_load"
        )
        min_room_load = model.NewIntVar(
            0, len(problem.presentations), "min_room_load"
        )
        room_imbalance = model.NewIntVar(
            0, len(problem.presentations), "room_imbalance"
        )
        model.AddMaxEquality(max_room_load, room_load_terms)
        model.AddMinEquality(min_room_load, room_load_terms)
        model.Add(room_imbalance == max_room_load - min_room_load)
        room_imbalance_terms.append(room_imbalance)

    model.Minimize(
        _objective_weighted_sum(
            makespan=makespan,
            soft_availability_terms=soft_availability_terms,
            class_span_terms=class_span_terms,
            professor_span_terms=professor_span_terms,
            room_imbalance_terms=room_imbalance_terms,
            horizon_slots=horizon_slots,
        )
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        suggestions = _build_admin_suggestions(
            problem=problem,
            diagnostics=("CP-SAT could not find a feasible schedule.",),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
        )
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=("CP-SAT could not find a feasible schedule.",),
            suggestions=suggestions,
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
