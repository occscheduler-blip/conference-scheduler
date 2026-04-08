from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import ceil

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)

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
    max_soft_availability = max(len(soft_availability_terms), 1) * max(
        len(soft_availability_terms), 1
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
    logger.info(
        "solve_schedule: presentations=%d  rooms=%d  windows=%d  time_limit=%.1fs",
        len(problem.presentations), problem.rooms_available, len(problem.symposium_windows), time_limit_seconds,
    )
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

    soft_violation_terms: list[cp_model.IntVar] = []
    _soft_violation_counter = 0

    def _add_constraint_or_penalty(
        expr_vars: list[cp_model.IntVar],
        mode: str,
        label: str,
    ) -> None:
        nonlocal _soft_violation_counter
        if not expr_vars:
            return
        if mode == "hard":
            model.Add(sum(expr_vars) <= 1)
        elif mode == "soft":
            violation = model.NewBoolVar(f"sv_{label}_{_soft_violation_counter}")
            _soft_violation_counter += 1
            model.Add(sum(expr_vars) <= 1).OnlyEnforceIf(violation.Not())
            soft_violation_terms.append(violation)

    if problem.constraints.same_class_same_room != "off":
        for class_id, class_presentations in presentations_by_class.items():
            if len(class_presentations) < 2:
                continue
            if problem.constraints.same_class_same_room == "hard":
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
            else:
                # Soft: penalize presentations whose room doesn't match the class room
                class_room_var = model.NewIntVar(
                    0, problem.rooms_available - 1, f"class_room_{class_id}"
                )
                for presentation in class_presentations:
                    deviation = model.NewBoolVar(
                        f"sv_class_{class_id}_{presentation.id}_{_soft_violation_counter}"
                    )
                    _soft_violation_counter += 1
                    for option_index in range(len(eligible_starts[presentation.id])):
                        for room_index in range(problem.rooms_available):
                            key = (presentation.id, option_index, room_index)
                            model.Add(class_room_var == room_index).OnlyEnforceIf(
                                assignment_vars[key], deviation.Not()
                            )
                    soft_violation_terms.append(deviation)

    all_instants = {
        instant
        for instant in all_instants
        if any(
            instant >= window.start and instant < window.end
            for window in symposium_windows
        )
    }

    for instant in sorted(all_instants):
        if problem.constraints.room_conflicts != "off":
            for room_index in range(problem.rooms_available):
                overlapping: list[cp_model.IntVar] = []
                for presentation in problem.presentations:
                    for option_index in range(len(eligible_starts[presentation.id])):
                        key = (presentation.id, option_index, room_index)
                        start_time, end_time = option_lookup[key]
                        buffered_end = end_time + timedelta(minutes=presentation.buffer_minutes)
                        if start_time <= instant < buffered_end:
                            overlapping.append(assignment_vars[key])
                _add_constraint_or_penalty(
                    overlapping, problem.constraints.room_conflicts, f"room_{room_index}_{instant}"
                )

        if problem.constraints.person_conflicts != "off":
            resources_at_time: dict[str, list[cp_model.IntVar]] = defaultdict(list)
            for presentation in problem.presentations:
                for resource_id in presentation.resource_ids:
                    for option_index in range(len(eligible_starts[presentation.id])):
                        for room_index in range(problem.rooms_available):
                            key = (presentation.id, option_index, room_index)
                            start_time, end_time = option_lookup[key]
                            if start_time <= instant < end_time:
                                resources_at_time[resource_id].append(assignment_vars[key])

            for resource_id, overlapping_res in resources_at_time.items():
                _add_constraint_or_penalty(
                    overlapping_res, problem.constraints.person_conflicts, f"person_{resource_id}_{instant}"
                )

    makespan = model.NewIntVar(0, 1000000, "makespan")
    model.AddMaxEquality(makespan, list(end_index_vars.values()))

    soft_availability_terms: list[cp_model.IntVar] = []
    if soft_resource_windows:
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
    if problem.constraints.minimize_class_span != "off":
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
            if problem.constraints.minimize_class_span == "hard":
                total_duration_slots = sum(
                    _slot_count(p.duration_minutes, problem.slot_minutes)
                    for p in class_presentations
                )
                model.Add(class_span <= total_duration_slots)
            else:
                class_span_terms.append(class_span)

    professor_span_terms: list[cp_model.IntVar] = []
    if problem.constraints.minimize_professor_span != "off":
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
            if problem.constraints.minimize_professor_span == "hard":
                total_duration_slots = sum(
                    _slot_count(p.duration_minutes, problem.slot_minutes)
                    for p in resource_presentations
                )
                model.Add(professor_span <= total_duration_slots)
            else:
                professor_span_terms.append(professor_span)

    room_load_terms: list[cp_model.IntVar] = []
    room_imbalance_terms: list[cp_model.IntVar] = []
    if problem.constraints.balance_rooms != "off" and problem.rooms_available > 1:
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
        if problem.constraints.balance_rooms == "hard":
            model.Add(room_imbalance <= 1)
        else:
            room_imbalance_terms.append(room_imbalance)

    makespan_for_objective = (
        makespan if problem.constraints.minimize_makespan == "soft" else model.NewConstant(0)
    )
    model.Minimize(
        _objective_weighted_sum(
            makespan=makespan_for_objective,
            soft_availability_terms=soft_availability_terms,
            class_span_terms=class_span_terms,
            professor_span_terms=professor_span_terms,
            room_imbalance_terms=room_imbalance_terms,
            horizon_slots=horizon_slots,
        )
        + sum(soft_violation_terms) * (horizon_slots ** 2)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds

    logger.info("Starting CP-SAT solver with %d variables", len(assignment_vars))
    status = solver.Solve(model)
    logger.info("CP-SAT solver finished: status=%s  wall_time=%.2fs", solver.StatusName(status), solver.WallTime())
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


def _availability_blocked_ids(result: ScheduleResult) -> frozenset[str]:
    """Return presentation IDs that failed availability filtering (pre-solver)."""
    return frozenset(
        pid
        for pid, diag in zip(
            result.unscheduled_presentations, result.diagnostics
        )
        if "no valid start times" in diag
    ) if result.unscheduled_presentations else frozenset()


def solve_schedule_with_relaxation(
    problem: ScheduleProblem, time_limit_seconds: float = 10.0
) -> ScheduleResult:
    """
    Attempt to solve the schedule, progressively relaxing constraints if infeasible.

    Relaxation order:
      1. (none) — strict solve
      2. Treat all resources as fully available for presentations that had no valid
         start times (availability-window conflict between presenter and professor).
      3. Remove the same-room constraint for classes that still have blocked
         presentations after relaxation 2.

    Each relaxation is reported in ScheduleResult.relaxations_applied.
    """
    relaxations: list[str] = []

    # ── Pass 1: strict ────────────────────────────────────────────────────────
    result = solve_schedule(problem, time_limit_seconds)
    if result.status in ("optimal", "feasible"):
        return result

    # ── Pass 2: relax resource availability for availability-blocked presentations ──
    blocked_ids = _availability_blocked_ids(result)
    if not blocked_ids:
        # CP-SAT itself failed (not a filtering issue); skip to pass 3
        blocked_ids = frozenset(p.id for p in problem.presentations)

    new_resource_windows = dict(problem.resource_windows)
    for pres in problem.presentations:
        if pres.id in blocked_ids:
            for rid in pres.resource_ids:
                new_resource_windows[rid] = problem.symposium_windows

    relaxed = replace(problem, resource_windows=new_resource_windows)
    n = len(blocked_ids)
    relaxations.append(
        f"Ignored resource availability for {n} presentation(s) with no valid time slots "
        f"— treated all their professors/students as available for the full symposium."
    )

    result = solve_schedule(relaxed, time_limit_seconds)
    if result.status in ("optimal", "feasible"):
        return replace(result, relaxations_applied=tuple(relaxations))

    # ── Pass 3: relax same-room constraint for affected classes ───────────────
    still_blocked = frozenset(result.unscheduled_presentations)
    affected_classes = {
        p.class_id
        for p in relaxed.presentations
        if p.id in still_blocked and p.class_id
    }

    if affected_classes:
        new_presentations = tuple(
            replace(p, class_id="") if p.class_id in affected_classes else p
            for p in relaxed.presentations
        )
        relaxed = replace(relaxed, presentations=new_presentations)
        relaxations.append(
            f"Removed same-room constraint for {len(affected_classes)} class(es) "
            f"({', '.join(sorted(affected_classes))}) — presentations from those "
            f"classes may now be scheduled in different rooms."
        )

        result = solve_schedule(relaxed, time_limit_seconds)
        if result.status in ("optimal", "feasible"):
            return replace(result, relaxations_applied=tuple(relaxations))

    # All relaxations exhausted
    return replace(
        result,
        status="infeasible",
        relaxations_applied=tuple(relaxations),
    )