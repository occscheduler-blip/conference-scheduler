from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil

from ortools.sat.python import cp_model
from app.utils import ensure_app_timezone

logger = logging.getLogger(__name__)

MAKESPAN_WEIGHT = 3
SOFT_AVAILABILITY_WEIGHT = 3
DEPARTMENT_SPAN_WEIGHT = 4
CLASS_SPAN_WEIGHT = 2
PROFESSOR_SPAN_WEIGHT = 2
ROOM_IMBALANCE_WEIGHT = 1
SOFT_CONSTRAINT_VIOLATION_WEIGHT = 5
SOFT_CONFLICT_SWEEP_MINUTES = 15
DEFAULT_SOLVER_WORKERS = 4
INT64_SAFE_OBJECTIVE_LIMIT = 4_000_000_000_000_000_000

from .models import (
    AvailabilityTimeframe,
    PresentationInput,
    ScheduledPresentation,
    ScheduleData,
    ScheduleResult,
)


def _EnsureUtc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return ensure_app_timezone(moment).astimezone(timezone.utc)
    return moment.astimezone(timezone.utc)


def _NormalizeTimeframes(
    timeframes: tuple[AvailabilityTimeframe, ...],
) -> tuple[AvailabilityTimeframe, ...]:
    normalized = tuple(
        sorted(
            (
                AvailabilityTimeframe(
                    start=_EnsureUtc(timeframe.start), end=_EnsureUtc(timeframe.end)
                )
                for timeframe in timeframes
                if timeframe.end > timeframe.start
            ),
            key=lambda timeframe: timeframe.start,
        )
    )
    return normalized


def _TimeframeContains(
    timeframes: tuple[AvailabilityTimeframe, ...], start: datetime, end: datetime
) -> bool:
    return any(start >= timeframe.start and end <= timeframe.end for timeframe in timeframes)


def _SlotCount(duration_minutes: int, slot_minutes: int) -> int:
    return ceil(duration_minutes / slot_minutes)


def _EligibleStarts(
    presentation: PresentationInput,
    symposium_timeframes: tuple[AvailabilityTimeframe, ...],
    resource_timeframes: dict[str, tuple[AvailabilityTimeframe, ...]],
    slot_minutes: int,
) -> tuple[datetime, ...]:
    starts: list[datetime] = []
    duration = timedelta(minutes=presentation.duration_minutes)
    step = timedelta(minutes=slot_minutes)

    for timeframe in symposium_timeframes:
        candidate = timeframe.start
        while candidate + duration <= timeframe.end:
            end = candidate + duration
            if all(
                _TimeframeContains(resource_timeframes[resource_id], candidate, end)
                for resource_id in presentation.resource_ids
                if resource_id in resource_timeframes
            ):
                starts.append(candidate)
            candidate += step

    return tuple(starts)


def _ObjectiveWeightedSum(
    makespan: cp_model.IntVar,
    soft_availability_terms: list[cp_model.IntVar],
    department_span_terms: list[cp_model.IntVar],
    class_span_terms: list[cp_model.IntVar],
    professor_span_terms: list[cp_model.IntVar],
    room_imbalance_terms: list[cp_model.IntVar],
    horizon_slots: int,  # kept for signature compatibility; no longer used for weights
) -> cp_model.LinearExpr:
    # Fixed small weights — no horizon_slots scaling.
    # Avoids int64 overflow when horizon_slots is large (e.g. 3360 with 1-min slots).
    # Department span weighted highest among grouping objectives so same-department
    # presentations cluster first, then same-class presentations cluster within.
    return (
        makespan * MAKESPAN_WEIGHT
        + sum(soft_availability_terms) * SOFT_AVAILABILITY_WEIGHT
        + sum(department_span_terms) * DEPARTMENT_SPAN_WEIGHT
        + sum(class_span_terms) * CLASS_SPAN_WEIGHT
        + sum(professor_span_terms) * PROFESSOR_SPAN_WEIGHT
        + sum(room_imbalance_terms) * ROOM_IMBALANCE_WEIGHT
    )


def _BuildAdminSuggestions(
    schedule_data: ScheduleData,
    diagnostics: tuple[str, ...],
    unscheduled_presentations: tuple[str, ...],
) -> tuple[str, ...]:
    suggestions: list[str] = []
    total_room_minutes = (
        sum(
            int((timeframe.end - timeframe.start).total_seconds() // 60)
            for timeframe in schedule_data.symposium_timeframes
        )
        * schedule_data.rooms_available
    )
    total_required_minutes = sum(
        presentation.duration_minutes + presentation.buffer_minutes
        for presentation in schedule_data.presentations
    )

    blocked_by_professor = any(
        "no valid start times" in message.lower()
        for message in diagnostics
    ) and bool(schedule_data.professor_resource_ids)
    if blocked_by_professor:
        suggestions.append(
            "Review professor availability timeframes for the blocked presentations or widen those windows in the admin settings."
        )

    class_ids = {presentation.class_id for presentation in schedule_data.presentations if presentation.class_id}
    if class_ids:
        suggestions.append(
            "Change the 'same class must stay in the same room' rule from hard to soft if you want the solver to use more rooms."
        )

    if any(presentation.buffer_minutes > 0 for presentation in schedule_data.presentations):
        suggestions.append(
            "Reduce the required room buffer between presentations, or make that rule softer, to free more scheduling options."
        )

    if schedule_data.soft_resource_timeframes:
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
        "Inspect the unscheduled presentations first and compare their durations, buffers, and attached people against the available timeframes.",
        "Keep 'all presentations must be scheduled' as a hard rule, and adjust time, rooms, or editable constraint settings around it.",
    )
    for suggestion in fallback_suggestions:
        if len(suggestions) >= 3:
            break
        if suggestion not in suggestions:
            suggestions.append(suggestion)

    return tuple(suggestions[:3])


@dataclass(frozen=True)
class _PreSolverResult:
    symposium_timeframes: tuple[AvailabilityTimeframe, ...] = ()
    resource_timeframes: dict[str, tuple[AvailabilityTimeframe, ...]] | None = None
    soft_resource_timeframes: dict[str, tuple[AvailabilityTimeframe, ...]] | None = None
    eligible_starts: dict[str, tuple[datetime, ...]] | None = None
    pre_unscheduled: tuple[str, ...] = ()
    schedulable_presentations: tuple[PresentationInput, ...] = ()
    diagnostics: tuple[str, ...] = ()
    failure_result: ScheduleResult | None = None


def _RunPreSolver(schedule_data: ScheduleData) -> _PreSolverResult:
    """Validate data and discover legal presentation start times."""
    if schedule_data.rooms_available < 1:
        return _PreSolverResult(
            failure_result=ScheduleResult(
                status="invalid",
                assignments=(),
                diagnostics=("rooms_available must be at least 1",),
            )
        )

    if schedule_data.slot_minutes < 1:
        return _PreSolverResult(
            failure_result=ScheduleResult(
                status="invalid",
                assignments=(),
                diagnostics=("slot_minutes must be at least 1",),
            )
        )

    symposium_timeframes = _NormalizeTimeframes(schedule_data.symposium_timeframes)
    if not symposium_timeframes:
        return _PreSolverResult(
            failure_result=ScheduleResult(
                status="infeasible",
                assignments=(),
                unscheduled_presentations=tuple(p.id for p in schedule_data.presentations),
                diagnostics=("No symposium availability timeframes were provided.",),
                suggestions=(
                    "Add at least one symposium timeframe before running the scheduler.",
                    "Increase the symposium date range if presentations need more placement options.",
                    "Review the scheduling settings and rerun after adding availability.",
                ),
            )
        )

    if not schedule_data.presentations:
        return _PreSolverResult(
            failure_result=ScheduleResult(
                status="optimal",
                assignments=(),
                diagnostics=("No presentations were provided.",),
            )
        )

    resource_timeframes = {
        resource_id: _NormalizeTimeframes(timeframes)
        for resource_id, timeframes in schedule_data.resource_timeframes.items()
    }
    soft_resource_timeframes = {
        resource_id: _NormalizeTimeframes(timeframes)
        for resource_id, timeframes in schedule_data.soft_resource_timeframes.items()
    }

    eligible_starts: dict[str, tuple[datetime, ...]] = {}
    pre_unscheduled: list[str] = []
    diagnostics: list[str] = []

    for presentation in schedule_data.presentations:
        if presentation.duration_minutes < 1:
            return _PreSolverResult(
                failure_result=ScheduleResult(
                    status="invalid",
                    assignments=(),
                    diagnostics=(f"Presentation {presentation.id} has an invalid duration.",),
                )
            )
        starts = _EligibleStarts(
            presentation=presentation,
            symposium_timeframes=symposium_timeframes,
            resource_timeframes=resource_timeframes,
            slot_minutes=schedule_data.slot_minutes,
        )
        eligible_starts[presentation.id] = starts
        if not starts:
            pre_unscheduled.append(presentation.id)
            diagnostics.append(
                f"Presentation {presentation.id} has no valid start times after availability filtering."
            )

    schedulable_presentations = tuple(
        presentation
        for presentation in schedule_data.presentations
        if eligible_starts[presentation.id]
    )
    if not schedulable_presentations:
        suggestions = _BuildAdminSuggestions(
            schedule_data=schedule_data,
            diagnostics=tuple(diagnostics),
            unscheduled_presentations=tuple(p.id for p in schedule_data.presentations),
        )
        return _PreSolverResult(
            failure_result=ScheduleResult(
                status="infeasible",
                assignments=(),
                unscheduled_presentations=tuple(p.id for p in schedule_data.presentations),
                diagnostics=tuple(diagnostics),
                suggestions=suggestions,
            )
        )

    return _PreSolverResult(
        symposium_timeframes=symposium_timeframes,
        resource_timeframes=resource_timeframes,
        soft_resource_timeframes=soft_resource_timeframes,
        eligible_starts=eligible_starts,
        pre_unscheduled=tuple(pre_unscheduled),
        schedulable_presentations=schedulable_presentations,
        diagnostics=tuple(diagnostics),
    )


def SolveSchedule(
    schedule_data: ScheduleData, time_limit_seconds: float = 30.0
) -> ScheduleResult:
    """Build and solve the CP-SAT schedule model.

    The solver follows a fixed sequence:
    validate the input data, discover valid placement options, create model
    variables, add hard constraints and soft penalties, set the objective, solve,
    and translate the selected variables back into schedule assignments.
    """
    logger.info(
        "SolveSchedule: presentations=%d  rooms=%d  timeframes=%d  time_limit=%.1fs",
        len(schedule_data.presentations), schedule_data.rooms_available, len(schedule_data.symposium_timeframes), time_limit_seconds,
    )

    # Validate data and discover valid starts before building the model.
    pre_solver = _RunPreSolver(schedule_data)
    if pre_solver.failure_result is not None:
        return pre_solver.failure_result

    symposium_timeframes = pre_solver.symposium_timeframes
    resource_timeframes = pre_solver.resource_timeframes or {}
    soft_resource_timeframes = pre_solver.soft_resource_timeframes or {}
    eligible_starts = pre_solver.eligible_starts or {}
    pre_unscheduled = list(pre_solver.pre_unscheduled)
    schedulable_presentations = list(pre_solver.schedulable_presentations)
    diagnostics = list(pre_solver.diagnostics)

    # Create model variables for presentation-room-time assignments.
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
    step = timedelta(minutes=schedule_data.slot_minutes)

    base_time = min(timeframe.start for timeframe in symposium_timeframes)
    horizon_slots = max(
        int((timeframe.end - base_time) / step) for timeframe in symposium_timeframes
    )

    for presentation in schedulable_presentations:
        option_indices: list[int] = []
        durations_slots = _SlotCount(
            presentation.duration_minutes, schedule_data.slot_minutes
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
                if resource_id in soft_resource_timeframes
                and not _TimeframeContains(
                    soft_resource_timeframes[resource_id], start_time, end_time
                )
            )
            for room_index in range(schedule_data.rooms_available):
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
            for room_index in range(schedule_data.rooms_available)
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
                for room_index in range(schedule_data.rooms_available)
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

    # Group presentations by department, class, and resource.
    presentations_by_department: dict[str, list[PresentationInput]] = defaultdict(list)
    presentations_by_class: dict[str, list[PresentationInput]] = defaultdict(list)
    presentations_by_resource: dict[str, list[PresentationInput]] = defaultdict(list)
    for presentation in schedulable_presentations:
        if presentation.department_id:
            presentations_by_department[presentation.department_id].append(presentation)
        if presentation.class_id:
            presentations_by_class[presentation.class_id].append(presentation)
        for resource_id in presentation.resource_ids:
            presentations_by_resource[resource_id].append(presentation)

    soft_violation_terms: list[cp_model.IntVar] = []
    _soft_violation_counter = 0

    def _AddHardAtMostOne(expr_vars: list[cp_model.IntVar]) -> None:
        if expr_vars:
            model.Add(sum(expr_vars) <= 1)

    def _AddSoftAtMostOnePenalty(
        expr_vars: list[cp_model.IntVar],
        label: str,
    ) -> None:
        nonlocal _soft_violation_counter
        if not expr_vars:
            return
        violation = model.NewBoolVar(f"sv_{label}_{_soft_violation_counter}")
        _soft_violation_counter += 1
        model.Add(sum(expr_vars) <= 1).OnlyEnforceIf(violation.Not())
        soft_violation_terms.append(violation)

    # Add class grouping constraints.
    if schedule_data.constraints.same_class_same_room != "off":
        for class_id, class_presentations in presentations_by_class.items():
            if len(class_presentations) < 2:
                continue
            if schedule_data.constraints.same_class_same_room == "hard":
                class_room_var = model.NewIntVar(
                    0, schedule_data.rooms_available - 1, f"class_room_{class_id}"
                )
                for presentation in class_presentations:
                    for option_index in range(len(eligible_starts[presentation.id])):
                        for room_index in range(schedule_data.rooms_available):
                            key = (presentation.id, option_index, room_index)
                            model.Add(class_room_var == room_index).OnlyEnforceIf(
                                assignment_vars[key]
                            )
            else:
                # Soft: penalize each pair of same-class presentations in different rooms
                for i, pres_a in enumerate(class_presentations):
                    for pres_b in class_presentations[i + 1:]:
                        for room_a in range(schedule_data.rooms_available):
                            for room_b in range(schedule_data.rooms_available):
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

    # Add hard room/person conflict constraints.
    # ── Hard constraints: AddNoOverlap (O(n log n)) ──────────────────────────
    # Replaces the old per-instant loop which was O(instants × presentations ×
    # options × rooms) — prohibitively slow with fine-grained slot alignment.

    if schedule_data.constraints.room_conflicts == "hard":
        for room_index in range(schedule_data.rooms_available):
            room_ivs: list[cp_model.IntervalVar] = []
            for presentation in schedulable_presentations:
                buf_slots = ceil(presentation.buffer_minutes / schedule_data.slot_minutes)
                dur_with_buf = (
                    _SlotCount(presentation.duration_minutes, schedule_data.slot_minutes)
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

    if schedule_data.constraints.person_conflicts == "hard":
        # One "option active" bool per (presentation, option): True iff this
        # presentation is scheduled at this option in any room.
        # sum(room_vars_for_opt) ∈ {0,1} (guaranteed by global at-most-one),
        # so `option_active = sum(room_vars_for_opt)` is a valid bool equation.
        option_active_vars: dict[tuple[str, int], cp_model.IntVar] = {}
        for presentation in schedulable_presentations:
            for option_index in range(len(eligible_starts[presentation.id])):
                room_vars_for_opt = [
                    assignment_vars[(presentation.id, option_index, r)]
                    for r in range(schedule_data.rooms_available)
                ]
                if schedule_data.rooms_available == 1:
                    option_active_vars[(presentation.id, option_index)] = room_vars_for_opt[0]
                else:
                    oa = model.NewBoolVar(f"oa_{presentation.id[:8]}_{option_index}")
                    model.Add(sum(room_vars_for_opt) == oa)
                    option_active_vars[(presentation.id, option_index)] = oa

        for resource_id, resource_presentations in presentations_by_resource.items():
            person_ivs: list[cp_model.IntervalVar] = []
            for presentation in resource_presentations:
                dur_slots = _SlotCount(
                    presentation.duration_minutes, schedule_data.slot_minutes
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

    # Add soft room/person conflict penalties.
    # ── Soft constraints: coarse soft-conflict sweep ────────────────────────────────
    # For soft room/person conflicts we fall back to a per-instant penalty
    # approach, but use SOFT_CONFLICT_SWEEP_MINUTES granularity regardless of slot_minutes to
    # keep model-build time bounded.
    if schedule_data.constraints.room_conflicts == "soft" or schedule_data.constraints.person_conflicts == "soft":
        coarse_step = timedelta(minutes=max(SOFT_CONFLICT_SWEEP_MINUTES, schedule_data.slot_minutes))
        soft_instants: set[datetime] = set()
        for timeframe in symposium_timeframes:
            t = timeframe.start
            while t < timeframe.end:
                soft_instants.add(t)
                t += coarse_step

        for instant in sorted(soft_instants):
            if schedule_data.constraints.room_conflicts == "soft":
                for room_index in range(schedule_data.rooms_available):
                    overlapping: list[cp_model.IntVar] = []
                    for presentation in schedulable_presentations:
                        for option_index in range(len(eligible_starts[presentation.id])):
                            key = (presentation.id, option_index, room_index)
                            start_time, end_time = option_lookup[key]
                            buffered_end = end_time + timedelta(minutes=presentation.buffer_minutes)
                            if start_time <= instant < buffered_end:
                                overlapping.append(assignment_vars[key])
                    _AddSoftAtMostOnePenalty(
                        overlapping, f"room_{room_index}_{instant}"
                    )

            if schedule_data.constraints.person_conflicts == "soft":
                resources_at_time: dict[str, list[cp_model.IntVar]] = defaultdict(list)
                for presentation in schedulable_presentations:
                    for resource_id in presentation.resource_ids:
                        for option_index in range(len(eligible_starts[presentation.id])):
                            for room_index in range(schedule_data.rooms_available):
                                key = (presentation.id, option_index, room_index)
                                start_time, end_time = option_lookup[key]
                                if start_time <= instant < end_time:
                                    resources_at_time[resource_id].append(
                                        assignment_vars[key]
                                    )
                for resource_id, overlapping_res in resources_at_time.items():
                    _AddSoftAtMostOnePenalty(
                        overlapping_res, f"person_{resource_id}_{instant}"
                    )

    logger.info("[solve-timing] conflict constraints: %.3fs", time.perf_counter() - t_slow)

    # Add schedule-quality terms.
    makespan = model.NewIntVar(0, horizon_slots, "makespan")
    model.AddMaxEquality(makespan, list(eff_end_for_max.values()))

    soft_availability_terms: list[cp_model.IntVar] = []
    if soft_resource_timeframes:
        total_soft_penalty = model.NewIntVar(
            0, len(schedulable_presentations) * max(len(soft_resource_timeframes), 1), "soft_availability_penalty"
        )
        model.Add(
            total_soft_penalty
            == sum(
                soft_penalty_lookup[(presentation.id, option_index)]
                * assignment_vars[(presentation.id, option_index, room_index)]
                for presentation in schedulable_presentations
                for option_index in range(len(eligible_starts[presentation.id]))
                for room_index in range(schedule_data.rooms_available)
            )
        )
        soft_availability_terms.append(total_soft_penalty)

    department_span_terms: list[cp_model.IntVar] = []
    if problem.constraints.minimize_department_span != "off":
        for dept_id, dept_presentations in presentations_by_department.items():
            if len(dept_presentations) < 2:
                continue
            dept_start = model.NewIntVar(0, horizon_slots, f"dept_start_{dept_id}")
            dept_end = model.NewIntVar(0, horizon_slots, f"dept_end_{dept_id}")
            dept_span = model.NewIntVar(0, horizon_slots, f"dept_span_{dept_id}")
            model.AddMinEquality(
                dept_start,
                [eff_start_for_min[p.id] for p in dept_presentations],
            )
            model.AddMaxEquality(
                dept_end,
                [eff_end_for_max[p.id] for p in dept_presentations],
            )
            model.Add(dept_span >= dept_end - dept_start)
            if problem.constraints.minimize_department_span == "hard":
                total_duration_slots = sum(
                    _slot_count(p.duration_minutes, problem.slot_minutes)
                    for p in dept_presentations
                )
                model.Add(dept_span <= total_duration_slots)
            else:
                department_span_terms.append(dept_span)

    class_span_terms: list[cp_model.IntVar] = []
    if schedule_data.constraints.minimize_class_span != "off":
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
            if schedule_data.constraints.minimize_class_span == "hard":
                total_duration_slots = sum(
                    _SlotCount(p.duration_minutes, schedule_data.slot_minutes)
                    for p in class_presentations
                )
                model.Add(class_span <= total_duration_slots)
            else:
                class_span_terms.append(class_span)

    professor_span_terms: list[cp_model.IntVar] = []
    if schedule_data.constraints.minimize_professor_span != "off":
        for resource_id in schedule_data.professor_resource_ids:
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
            if schedule_data.constraints.minimize_professor_span == "hard":
                total_duration_slots = sum(
                    _SlotCount(p.duration_minutes, schedule_data.slot_minutes)
                    for p in resource_presentations
                )
                model.Add(professor_span <= total_duration_slots)
            else:
                professor_span_terms.append(professor_span)

    room_load_terms: list[cp_model.IntVar] = []
    room_imbalance_terms: list[cp_model.IntVar] = []
    if schedule_data.constraints.balance_rooms != "off" and schedule_data.rooms_available > 1:
        for room_index in range(schedule_data.rooms_available):
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
        if schedule_data.constraints.balance_rooms == "hard":
            model.Add(room_imbalance <= 1)
        else:
            room_imbalance_terms.append(room_imbalance)

    makespan_for_objective = (
        makespan if schedule_data.constraints.minimize_makespan == "soft" else model.NewConstant(0)
    )
    # Set objective.
    quality_objective = (
        _ObjectiveWeightedSum(
            makespan=makespan_for_objective,
            soft_availability_terms=soft_availability_terms,
            department_span_terms=department_span_terms,
            class_span_terms=class_span_terms,
            professor_span_terms=professor_span_terms,
            room_imbalance_terms=room_imbalance_terms,
            horizon_slots=horizon_slots,
        )
        + sum(soft_violation_terms) * SOFT_CONSTRAINT_VIOLATION_WEIGHT
    )

    # Scheduling as many presentations as possible takes top priority.
    # The penalty per unscheduled presentation must exceed any possible gain from
    # the quality objective.  Because we now use fixed weights (not horizon-based
    # polynomials), the maximum of quality_objective is straightforward to bound:
    #   makespan        : <= horizon_slots * MAKESPAN_WEIGHT
    #   soft_avail      : <= n_schedulable * n_soft_resources * SOFT_AVAILABILITY_WEIGHT
    #   dept_span       : <= n_department_terms * horizon_slots * DEPARTMENT_SPAN_WEIGHT
    #   class_span      : <= n_class_terms * horizon_slots * CLASS_SPAN_WEIGHT
    #   professor_span  : <= n_prof_terms * horizon_slots * PROFESSOR_SPAN_WEIGHT
    #   room_imbalance  : <= n_schedulable * ROOM_IMBALANCE_WEIGHT
    #   soft_violations : <= len(soft_violation_terms) * SOFT_CONSTRAINT_VIOLATION_WEIGHT
    n_schedulable = len(schedulable_presentations)
    _max_quality = (
        horizon_slots * MAKESPAN_WEIGHT
        + n_schedulable * max(len(soft_resource_timeframes), 1) * SOFT_AVAILABILITY_WEIGHT
        + len(department_span_terms) * horizon_slots * DEPARTMENT_SPAN_WEIGHT
        + len(class_span_terms) * horizon_slots * CLASS_SPAN_WEIGHT
        + len(professor_span_terms) * horizon_slots * PROFESSOR_SPAN_WEIGHT
        + n_schedulable * ROOM_IMBALANCE_WEIGHT
        + len(soft_violation_terms) * SOFT_CONSTRAINT_VIOLATION_WEIGHT
    )
    # Weight must beat the best possible quality improvement from the entire
    # quality_objective, so that scheduling one more presentation is always
    # preferred over any quality gain.  Clamped so the total penalty term
    # n_schedulable × weight stays well within CP-SAT's int64 domain.
    scheduling_penalty_weight = min(
        _max_quality + 1,
        INT64_SAFE_OBJECTIVE_LIMIT // max(n_schedulable, 1),
    )

    unscheduled_count = n_schedulable - sum(is_scheduled_vars.values())
    model.Minimize(unscheduled_count * scheduling_penalty_weight + quality_objective)

    # Solve model.
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = DEFAULT_SOLVER_WORKERS

    logger.info("Starting CP-SAT solver with %d variables", len(assignment_vars))
    status = solver.Solve(model)
    logger.info("CP-SAT solver finished: status=%s  wall_time=%.2fs", solver.StatusName(status), solver.WallTime())
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        all_unscheduled = tuple(
            pre_unscheduled + [p.id for p in schedulable_presentations]
        )
        suggestions = _BuildAdminSuggestions(
            schedule_data=schedule_data,
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

    # Translate solver variables into output assignments.
    assignments: list[ScheduledPresentation] = []
    cp_sat_unscheduled: list[str] = []
    for presentation in schedulable_presentations:
        if solver.Value(is_scheduled_vars[presentation.id]) == 0:
            cp_sat_unscheduled.append(presentation.id)
            continue
        for option_index in range(len(eligible_starts[presentation.id])):
            for room_index in range(schedule_data.rooms_available):
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


solve_schedule = SolveSchedule
