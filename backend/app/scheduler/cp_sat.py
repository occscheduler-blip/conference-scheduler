from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil

from ortools.sat.python import cp_model
from app.utils import ensure_app_timezone

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
        return ensure_app_timezone(moment).astimezone(timezone.utc)
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
    horizon_slots: int,  # kept for signature compatibility; no longer used for weights
) -> cp_model.LinearExpr:
    # Fixed small weights — no horizon_slots scaling.
    # Avoids int64 overflow when horizon_slots is large (e.g. 3360 with 1-min slots).
    # The exact ordering doesn't matter for correctness; the scheduling penalty
    # term dominates so these weights only act as tie-breakers among feasible schedules.
    _W_MAKESPAN = 3
    _W_AVAIL = 3
    _W_CLASS = 2
    _W_PROF = 2
    _W_ROOM = 1
    return (
        makespan * _W_MAKESPAN
        + sum(soft_availability_terms) * _W_AVAIL
        + sum(class_span_terms) * _W_CLASS
        + sum(professor_span_terms) * _W_PROF
        + sum(room_imbalance_terms) * _W_ROOM
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
    problem: ScheduleProblem, time_limit_seconds: float = 30.0
) -> ScheduleResult:
    logger.info(
        "solve_schedule: presentations=%d  rooms=%d  windows=%d  time_limit=%.1fs",
        len(problem.presentations), problem.rooms_available, len(problem.symposium_windows), time_limit_seconds,
    )

    # Immediately fail if schedule is impossible to make
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

    # Presentations with no valid start times are pre-marked as unschedulable.
    # We continue with the rest rather than aborting entirely.
    pre_unscheduled: list[str] = list(unschedulable)
    schedulable_presentations = [
        p for p in problem.presentations if eligible_starts[p.id]
    ]

    if not schedulable_presentations:
        suggestions = _build_admin_suggestions(
            problem=problem,
            diagnostics=tuple(diagnostics),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
        )
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=tuple(diagnostics),
            suggestions=suggestions,
        )

    model = cp_model.CpModel()
    assignment_vars: dict[tuple[str, int, int], cp_model.IntVar] = {}
    is_scheduled_vars: dict[str, cp_model.IntVar] = {}
    start_index_vars: dict[str, cp_model.IntVar] = {}
    end_index_vars: dict[str, cp_model.IntVar] = {}
    # Sentinel vars: eff_start_for_min = horizon_slots when unscheduled (safe for AddMinEquality)
    #                eff_end_for_max   = 0             when unscheduled (safe for AddMaxEquality)
    eff_start_for_min: dict[str, cp_model.IntVar] = {}
    eff_end_for_max: dict[str, cp_model.IntVar] = {}
    option_lookup: dict[tuple[str, int, int], tuple[datetime, datetime]] = {}
    soft_penalty_lookup: dict[tuple[str, int], int] = {}
    all_instants: set[datetime] = set()
    step = timedelta(minutes=problem.slot_minutes)

    base_time = min(window.start for window in symposium_windows)
    horizon_slots = max(
        int((window.end - base_time) / step) for window in symposium_windows
    )

    for presentation in schedulable_presentations:
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
        # Each presentation may be scheduled (sum=1) or skipped (sum=0).
        # is_sched == sum of all assignment vars (0 or 1) — single linear constraint.
        all_assign_for_p = [
            assignment_vars[(presentation.id, option_index, room_index)]
            for option_index in range(len(eligible_starts[presentation.id]))
            for room_index in range(problem.rooms_available)
        ]
        is_sched = model.NewBoolVar(f"is_sched_{presentation.id}")
        is_scheduled_vars[presentation.id] = is_sched
        model.Add(sum(all_assign_for_p) == is_sched)

        # Domain must include 0 so that start_index=0 is valid when unscheduled.
        start_index = model.NewIntVar(
            0,
            max(option_indices),
            f"start_slot_{presentation.id}",
        )
        end_index = model.NewIntVar(
            0,
            max(option_indices) + durations_slots,
            f"end_slot_{presentation.id}",
        )
        start_index_vars[presentation.id] = start_index
        end_index_vars[presentation.id] = end_index
        # When scheduled, start_index equals the chosen option's slot; when unscheduled, sum=0.
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

        # Sentinel effective vars for AddMinEquality / AddMaxEquality — linear formulation.
        # eff_start_for_min = start_index when scheduled, horizon_slots when not.
        # eff_end_for_max   = end_index   when scheduled, 0           when not.
        eff_smin = model.NewIntVar(0, horizon_slots, f"eff_smin_{presentation.id}")
        # eff_smin = start_index + horizon_slots * (1 - is_sched)
        #          = start_index + horizon_slots - horizon_slots * is_sched
        model.Add(eff_smin == start_index + horizon_slots - horizon_slots * is_sched)
        eff_start_for_min[presentation.id] = eff_smin

        eff_emax = model.NewIntVar(0, horizon_slots, f"eff_emax_{presentation.id}")
        # eff_emax = end_index when is_sched=1, pushed to 0 when is_sched=0 (objective drives it).
        # Big-M: eff_emax <= end_index  AND  eff_emax >= end_index - horizon_slots*(1-is_sched)
        model.Add(eff_emax <= end_index)
        model.Add(eff_emax >= end_index - horizon_slots + horizon_slots * is_sched)
        eff_end_for_max[presentation.id] = eff_emax

    # Group presentations by class and enforce same-room constraint.
    presentations_by_class: dict[str, list[PresentationInput]] = defaultdict(list)
    presentations_by_resource: dict[str, list[PresentationInput]] = defaultdict(list)
    for presentation in schedulable_presentations:
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
                # Soft: penalize each pair of same-class presentations in different rooms
                for i, pres_a in enumerate(class_presentations):
                    for pres_b in class_presentations[i + 1:]:
                        for room_a in range(problem.rooms_available):
                            for room_b in range(problem.rooms_available):
                                if room_a == room_b:
                                    continue
                                for oi_a in range(len(eligible_starts[pres_a.id])):
                                    for oi_b in range(len(eligible_starts[pres_b.id])):
                                        key_a = (pres_a.id, oi_a, room_a)
                                        key_b = (pres_b.id, oi_b, room_b)
                                        violation = model.NewBoolVar(
                                            f"sv_class_{class_id}_{_soft_violation_counter}"
                                        )
                                        _soft_violation_counter += 1
                                        # both assigned to different rooms → violation
                                        model.AddBoolOr([
                                            assignment_vars[key_a].Not(),
                                            assignment_vars[key_b].Not(),
                                            violation,
                                        ])
                                        soft_violation_terms.append(violation)

    t_slow = time.perf_counter()

    # ── Hard constraints: AddNoOverlap (O(n log n)) ──────────────────────────
    # Replaces the old per-instant loop which was O(instants × presentations ×
    # options × rooms) — prohibitively slow with fine-grained slot alignment.

    if problem.constraints.room_conflicts == "hard":
        for room_index in range(problem.rooms_available):
            room_ivs: list[cp_model.IntervalVar] = []
            for presentation in schedulable_presentations:
                buf_slots = ceil(presentation.buffer_minutes / problem.slot_minutes)
                dur_with_buf = (
                    _slot_count(presentation.duration_minutes, problem.slot_minutes)
                    + buf_slots
                )
                for option_index in range(len(eligible_starts[presentation.id])):
                    key = (presentation.id, option_index, room_index)
                    start_slot = int(
                        (eligible_starts[presentation.id][option_index] - base_time) / step
                    )
                    iv = model.NewOptionalFixedSizeIntervalVar(
                        start_slot,
                        dur_with_buf,
                        assignment_vars[key],
                        f"riv_{presentation.id[:8]}_{option_index}_{room_index}",
                    )
                    room_ivs.append(iv)
            model.AddNoOverlap(room_ivs)

    if problem.constraints.person_conflicts == "hard":
        # One "option active" bool per (presentation, option): True iff this
        # presentation is scheduled at this option in any room.
        # sum(room_vars_for_opt) ∈ {0,1} (guaranteed by global at-most-one),
        # so `option_active = sum(room_vars_for_opt)` is a valid bool equation.
        option_active_vars: dict[tuple[str, int], cp_model.IntVar] = {}
        for presentation in schedulable_presentations:
            for option_index in range(len(eligible_starts[presentation.id])):
                room_vars_for_opt = [
                    assignment_vars[(presentation.id, option_index, r)]
                    for r in range(problem.rooms_available)
                ]
                if problem.rooms_available == 1:
                    option_active_vars[(presentation.id, option_index)] = room_vars_for_opt[0]
                else:
                    oa = model.NewBoolVar(f"oa_{presentation.id[:8]}_{option_index}")
                    model.Add(sum(room_vars_for_opt) == oa)
                    option_active_vars[(presentation.id, option_index)] = oa

        for resource_id, resource_presentations in presentations_by_resource.items():
            person_ivs: list[cp_model.IntervalVar] = []
            for presentation in resource_presentations:
                dur_slots = _slot_count(
                    presentation.duration_minutes, problem.slot_minutes
                )
                for option_index in range(len(eligible_starts[presentation.id])):
                    start_slot = int(
                        (eligible_starts[presentation.id][option_index] - base_time) / step
                    )
                    active = option_active_vars[(presentation.id, option_index)]
                    iv = model.NewOptionalFixedSizeIntervalVar(
                        start_slot,
                        dur_slots,
                        active,
                        f"piv_{resource_id[:8]}_{presentation.id[:8]}_{option_index}",
                    )
                    person_ivs.append(iv)
            if len(person_ivs) > 1:
                model.AddNoOverlap(person_ivs)

    # ── Soft constraints: coarse 15-min sweep ────────────────────────────────
    # For soft room/person conflicts we fall back to a per-instant penalty
    # approach, but use 15-minute granularity regardless of slot_minutes to
    # keep model-build time bounded.
    if problem.constraints.room_conflicts == "soft" or problem.constraints.person_conflicts == "soft":
        coarse_step = timedelta(minutes=max(15, problem.slot_minutes))
        soft_instants: set[datetime] = set()
        for window in symposium_windows:
            t = window.start
            while t < window.end:
                soft_instants.add(t)
                t += coarse_step

        for instant in sorted(soft_instants):
            if problem.constraints.room_conflicts == "soft":
                for room_index in range(problem.rooms_available):
                    overlapping: list[cp_model.IntVar] = []
                    for presentation in schedulable_presentations:
                        for option_index in range(len(eligible_starts[presentation.id])):
                            key = (presentation.id, option_index, room_index)
                            start_time, end_time = option_lookup[key]
                            buffered_end = end_time + timedelta(minutes=presentation.buffer_minutes)
                            if start_time <= instant < buffered_end:
                                overlapping.append(assignment_vars[key])
                    _add_constraint_or_penalty(
                        overlapping, "soft", f"room_{room_index}_{instant}"
                    )

            if problem.constraints.person_conflicts == "soft":
                resources_at_time: dict[str, list[cp_model.IntVar]] = defaultdict(list)
                for presentation in schedulable_presentations:
                    for resource_id in presentation.resource_ids:
                        for option_index in range(len(eligible_starts[presentation.id])):
                            for room_index in range(problem.rooms_available):
                                key = (presentation.id, option_index, room_index)
                                start_time, end_time = option_lookup[key]
                                if start_time <= instant < end_time:
                                    resources_at_time[resource_id].append(
                                        assignment_vars[key]
                                    )
                for resource_id, overlapping_res in resources_at_time.items():
                    _add_constraint_or_penalty(
                        overlapping_res, "soft", f"person_{resource_id}_{instant}"
                    )

    logger.info("[solve-timing] conflict constraints: %.3fs", time.perf_counter() - t_slow)

    makespan = model.NewIntVar(0, 1000000, "makespan")
    model.AddMaxEquality(makespan, list(eff_end_for_max.values()))

    soft_availability_terms: list[cp_model.IntVar] = []
    if soft_resource_windows:
        total_soft_penalty = model.NewIntVar(
            0, len(schedulable_presentations) * max(len(soft_resource_windows), 1), "soft_availability_penalty"
        )
        model.Add(
            total_soft_penalty
            == sum(
                soft_penalty_lookup[(presentation.id, option_index)]
                * assignment_vars[(presentation.id, option_index, room_index)]
                for presentation in schedulable_presentations
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
                [eff_start_for_min[presentation.id] for presentation in class_presentations],
            )
            model.AddMaxEquality(
                class_end,
                [eff_end_for_max[presentation.id] for presentation in class_presentations],
            )
            # >= instead of == so that class_span=0 is valid when all presentations are unscheduled
            # (which would make class_end - class_start negative with sentinel values).
            model.Add(class_span >= class_end - class_start)
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
                [eff_start_for_min[presentation.id] for presentation in resource_presentations],
            )
            model.AddMaxEquality(
                professor_end,
                [eff_end_for_max[presentation.id] for presentation in resource_presentations],
            )
            model.Add(professor_span >= professor_end - professor_start)
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
                0, len(schedulable_presentations), f"room_load_{room_index}"
            )
            model.Add(
                room_load
                == sum(
                    assignment_vars[(presentation.id, option_index, room_index)]
                    for presentation in schedulable_presentations
                    for option_index in range(len(eligible_starts[presentation.id]))
                )
            )
            room_load_terms.append(room_load)

        max_room_load = model.NewIntVar(
            0, len(schedulable_presentations), "max_room_load"
        )
        min_room_load = model.NewIntVar(
            0, len(schedulable_presentations), "min_room_load"
        )
        room_imbalance = model.NewIntVar(
            0, len(schedulable_presentations), "room_imbalance"
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
    # Fixed weight for soft constraint violations (same-class-same-room, etc.)
    # Must be > 0 but kept small so it never exceeds the scheduling penalty.
    _W_SOFT_VIO = 5
    quality_objective = (
        _objective_weighted_sum(
            makespan=makespan_for_objective,
            soft_availability_terms=soft_availability_terms,
            class_span_terms=class_span_terms,
            professor_span_terms=professor_span_terms,
            room_imbalance_terms=room_imbalance_terms,
            horizon_slots=horizon_slots,
        )
        + sum(soft_violation_terms) * _W_SOFT_VIO
    )

    # Scheduling as many presentations as possible takes top priority.
    # The penalty per unscheduled presentation must exceed any possible gain from
    # the quality objective.  Because we now use fixed weights (not horizon-based
    # polynomials), the maximum of quality_objective is straightforward to bound:
    #   makespan      : ≤ horizon_slots × _W_MAKESPAN (3)
    #   soft_avail    : ≤ n_schedulable × n_soft_resources × _W_AVAIL (3)
    #   class_span    : ≤ n_class_terms × horizon_slots × _W_CLASS (2)
    #   prof_span     : ≤ n_prof_terms  × horizon_slots × _W_PROF  (2)
    #   room_imbalance: ≤ n_schedulable × _W_ROOM (1)
    #   soft_violations: ≤ len(soft_violation_terms) × _W_SOFT_VIO (5)
    _INT64_SAFE = 4_000_000_000_000_000_000  # well under int64 max (≈9.2e18)
    n_schedulable = len(schedulable_presentations)
    _max_quality = (
        horizon_slots * 3  # makespan × _W_MAKESPAN
        + n_schedulable * max(len(soft_resource_windows), 1) * 3  # soft_avail × _W_AVAIL
        + len(class_span_terms) * horizon_slots * 2  # class_span × _W_CLASS
        + len(professor_span_terms) * horizon_slots * 2  # prof_span × _W_PROF
        + n_schedulable * 1  # room_imbalance × _W_ROOM
        + len(soft_violation_terms) * _W_SOFT_VIO
    )
    # Weight must beat the best possible quality improvement from the entire
    # quality_objective, so that scheduling one more presentation is always
    # preferred over any quality gain.  Clamped so the total penalty term
    # n_schedulable × weight stays well within CP-SAT's int64 domain.
    scheduling_penalty_weight = min(
        _max_quality + 1,
        _INT64_SAFE // max(n_schedulable, 1),
    )

    unscheduled_count = n_schedulable - sum(is_scheduled_vars.values())
    model.Minimize(unscheduled_count * scheduling_penalty_weight + quality_objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 4

    logger.info("Starting CP-SAT solver with %d variables", len(assignment_vars))
    status = solver.Solve(model)
    logger.info("CP-SAT solver finished: status=%s  wall_time=%.2fs", solver.StatusName(status), solver.WallTime())
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        all_unscheduled = tuple(
            pre_unscheduled + [p.id for p in schedulable_presentations]
        )
        suggestions = _build_admin_suggestions(
            problem=problem,
            diagnostics=("CP-SAT could not find a feasible schedule.",),
            unscheduled_presentations=all_unscheduled,
        )
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=all_unscheduled,
            diagnostics=("CP-SAT could not find a feasible schedule.",),
            suggestions=suggestions,
        )

    assignments: list[ScheduledPresentation] = []
    cp_sat_unscheduled: list[str] = []
    for presentation in schedulable_presentations:
        if solver.Value(is_scheduled_vars[presentation.id]) == 0:
            cp_sat_unscheduled.append(presentation.id)
            continue
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
    all_unscheduled = tuple(pre_unscheduled + cp_sat_unscheduled)
    if all_unscheduled:
        logger.info(
            "Partial schedule: %d scheduled, %d unscheduled (%d pre-filtered, %d cp-sat-skipped)",
            len(assignments),
            len(all_unscheduled),
            len(pre_unscheduled),
            len(cp_sat_unscheduled),
        )
    return ScheduleResult(
        status=result_status,
        assignments=tuple(assignments),
        unscheduled_presentations=all_unscheduled,
        diagnostics=tuple(diagnostics),
    )

