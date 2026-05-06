"""Quality measurements and soft-constraint satisfaction scoring.

Two layers:

1. `measure_quality` — raw numbers (makespan, spans, room loads, etc.)
2. `score_soft_constraints` — normalize each soft objective to a 0.0–1.0
   satisfaction score where 1.0 is the best plausible outcome and 0.0 is
   the worst.

Aggregated as a geometric mean — `aggregate_soft_score` — for one-number
trend tracking.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from app.scheduler.models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduleProblem,
    ScheduleResult,
    ScheduledPresentation,
)


@dataclass(frozen=True)
class QualityMetrics:
    scheduled_count: int
    total_count: int
    scheduled_pct: float
    unscheduled_count: int
    wall_time_seconds: float
    makespan_minutes: float
    max_makespan_per_room_minutes: float
    dept_span_max_minutes: float
    dept_span_avg_minutes: float
    class_span_max_minutes: float
    class_span_avg_minutes: float
    prof_span_max_minutes: float
    prof_span_avg_minutes: float
    room_load_count_imbalance: int
    room_load_minutes_imbalance: float
    soft_availability_violations: int
    unscheduled_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "scheduled_count": self.scheduled_count,
            "total_count": self.total_count,
            "scheduled_pct": round(self.scheduled_pct, 4),
            "unscheduled_count": self.unscheduled_count,
            "wall_time_seconds": round(self.wall_time_seconds, 3),
            "makespan_minutes": round(self.makespan_minutes, 1),
            "max_makespan_per_room_minutes": round(self.max_makespan_per_room_minutes, 1),
            "dept_span_max_minutes": round(self.dept_span_max_minutes, 1),
            "dept_span_avg_minutes": round(self.dept_span_avg_minutes, 1),
            "class_span_max_minutes": round(self.class_span_max_minutes, 1),
            "class_span_avg_minutes": round(self.class_span_avg_minutes, 1),
            "prof_span_max_minutes": round(self.prof_span_max_minutes, 1),
            "prof_span_avg_minutes": round(self.prof_span_avg_minutes, 1),
            "room_load_count_imbalance": self.room_load_count_imbalance,
            "room_load_minutes_imbalance": round(self.room_load_minutes_imbalance, 1),
            "soft_availability_violations": self.soft_availability_violations,
            "unscheduled_ids": list(self.unscheduled_ids),
        }


@dataclass(frozen=True)
class SoftScores:
    scheduling_completeness: float
    minimize_makespan: float
    minimize_dept_span: float
    minimize_class_span: float
    minimize_prof_span: float
    balance_rooms: float
    student_availability: float
    aggregate_soft_score: float

    def to_dict(self) -> dict[str, float]:
        return {
            "scheduling_completeness": round(self.scheduling_completeness, 4),
            "minimize_makespan": round(self.minimize_makespan, 4),
            "minimize_dept_span": round(self.minimize_dept_span, 4),
            "minimize_class_span": round(self.minimize_class_span, 4),
            "minimize_prof_span": round(self.minimize_prof_span, 4),
            "balance_rooms": round(self.balance_rooms, 4),
            "student_availability": round(self.student_availability, 4),
            "aggregate_soft_score": round(self.aggregate_soft_score, 4),
        }


# ── Helpers ───────────────────────────────────────────────────────────────


def _minutes(seconds: float) -> float:
    return seconds / 60.0


def _within_any_window(
    start, end, windows: Iterable[AvailabilityWindow]
) -> bool:
    return any(start >= w.start and end <= w.end for w in windows)


def _spans_per_group(
    assignments: list[ScheduledPresentation],
    pres_by_id: dict[str, PresentationInput],
    group_key,
) -> list[float]:
    """Return per-group `(last_end - first_start)` in minutes."""
    by_group: dict[str, list[ScheduledPresentation]] = defaultdict(list)
    for a in assignments:
        pres = pres_by_id.get(a.presentation_id)
        if pres is None:
            continue
        keys = group_key(pres)
        if isinstance(keys, str):
            keys = [keys] if keys else []
        for k in keys:
            by_group[k].append(a)
    spans: list[float] = []
    for items in by_group.values():
        if not items:
            continue
        first = min(i.start for i in items)
        last = max(i.end for i in items)
        spans.append(_minutes((last - first).total_seconds()))
    return spans


def _group_lower_bound_minutes(
    presentations: Iterable[PresentationInput],
    group_key,
) -> dict[str, float]:
    """For each group, the minimum achievable span = sum(durations + intra-buffers).

    Buffers are conservatively counted between every pair within the group.
    """
    by_group: dict[str, list[PresentationInput]] = defaultdict(list)
    for p in presentations:
        keys = group_key(p)
        if isinstance(keys, str):
            keys = [keys] if keys else []
        for k in keys:
            by_group[k].append(p)
    out: dict[str, float] = {}
    for k, items in by_group.items():
        total = sum(p.duration_minutes for p in items)
        if len(items) > 1:
            # Conservative intra-group buffer.
            total += sum(p.buffer_minutes for p in items[:-1])
        out[k] = float(total)
    return out


# ── Raw measurements ──────────────────────────────────────────────────────


def measure_quality(
    problem: ScheduleProblem,
    result: ScheduleResult,
    wall_time_seconds: float,
) -> QualityMetrics:
    pres_by_id = {p.id: p for p in problem.presentations}
    total = len(problem.presentations)
    scheduled_count = len(result.assignments)
    unscheduled_count = total - scheduled_count
    scheduled_pct = scheduled_count / total if total > 0 else 1.0

    if not result.assignments:
        return QualityMetrics(
            scheduled_count=scheduled_count,
            total_count=total,
            scheduled_pct=scheduled_pct,
            unscheduled_count=unscheduled_count,
            wall_time_seconds=wall_time_seconds,
            makespan_minutes=0.0,
            max_makespan_per_room_minutes=0.0,
            dept_span_max_minutes=0.0,
            dept_span_avg_minutes=0.0,
            class_span_max_minutes=0.0,
            class_span_avg_minutes=0.0,
            prof_span_max_minutes=0.0,
            prof_span_avg_minutes=0.0,
            room_load_count_imbalance=0,
            room_load_minutes_imbalance=0.0,
            soft_availability_violations=0,
            unscheduled_ids=tuple(result.unscheduled_presentations),
        )

    assignments = list(result.assignments)
    first = min(a.start for a in assignments)
    last = max(a.end for a in assignments)
    makespan = _minutes((last - first).total_seconds())

    # Per-room makespan
    by_room: dict[int, list[ScheduledPresentation]] = defaultdict(list)
    for a in assignments:
        by_room[a.room_index].append(a)
    room_makespans = []
    room_load_counts: list[int] = []
    room_load_minutes: list[float] = []
    for room_index in range(problem.rooms_available):
        items = by_room.get(room_index, [])
        if items:
            first_r = min(i.start for i in items)
            last_r = max(i.end for i in items)
            room_makespans.append(_minutes((last_r - first_r).total_seconds()))
        else:
            room_makespans.append(0.0)
        room_load_counts.append(len(items))
        room_load_minutes.append(
            sum(_minutes((i.end - i.start).total_seconds()) for i in items)
        )
    max_room_makespan = max(room_makespans) if room_makespans else 0.0

    # Spans by department / class / professor.
    dept_spans = _spans_per_group(
        assignments, pres_by_id, lambda p: p.department_id
    )
    class_spans = _spans_per_group(
        assignments, pres_by_id, lambda p: p.class_id
    )
    prof_set = set(problem.professor_resource_ids)

    def prof_keys(p: PresentationInput) -> list[str]:
        identity = problem.resource_identity or {}
        return [
            identity.get(rid, rid) for rid in p.resource_ids if rid in prof_set
        ]

    prof_spans = _spans_per_group(assignments, pres_by_id, prof_keys)

    # Room imbalance.
    room_count_imbalance = (
        max(room_load_counts) - min(room_load_counts) if room_load_counts else 0
    )
    room_minutes_imbalance = (
        max(room_load_minutes) - min(room_load_minutes) if room_load_minutes else 0.0
    )

    # Soft-availability violations: presentations placed outside a
    # soft_resource_window for any of their resources that had a soft window.
    soft_violations = 0
    for a in assignments:
        pres = pres_by_id.get(a.presentation_id)
        if pres is None:
            continue
        for rid in pres.resource_ids:
            soft_windows = problem.soft_resource_windows.get(rid)
            if soft_windows and not _within_any_window(a.start, a.end, soft_windows):
                soft_violations += 1
                break  # count each presentation at most once

    return QualityMetrics(
        scheduled_count=scheduled_count,
        total_count=total,
        scheduled_pct=scheduled_pct,
        unscheduled_count=unscheduled_count,
        wall_time_seconds=wall_time_seconds,
        makespan_minutes=makespan,
        max_makespan_per_room_minutes=max_room_makespan,
        dept_span_max_minutes=max(dept_spans) if dept_spans else 0.0,
        dept_span_avg_minutes=sum(dept_spans) / len(dept_spans) if dept_spans else 0.0,
        class_span_max_minutes=max(class_spans) if class_spans else 0.0,
        class_span_avg_minutes=sum(class_spans) / len(class_spans) if class_spans else 0.0,
        prof_span_max_minutes=max(prof_spans) if prof_spans else 0.0,
        prof_span_avg_minutes=sum(prof_spans) / len(prof_spans) if prof_spans else 0.0,
        room_load_count_imbalance=room_count_imbalance,
        room_load_minutes_imbalance=room_minutes_imbalance,
        soft_availability_violations=soft_violations,
        unscheduled_ids=tuple(result.unscheduled_presentations),
    )


# ── Soft-constraint satisfaction scoring ──────────────────────────────────


def _clamp01(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        return 0.0
    return max(0.0, min(1.0, x))


def _total_horizon_minutes(problem: ScheduleProblem) -> float:
    if not problem.symposium_windows:
        return 0.0
    first = min(w.start for w in problem.symposium_windows)
    last = max(w.end for w in problem.symposium_windows)
    return _minutes((last - first).total_seconds())


def _makespan_lower_bound_minutes(problem: ScheduleProblem) -> float:
    if not problem.presentations or problem.rooms_available <= 0:
        return 0.0
    total_minutes = sum(p.duration_minutes for p in problem.presentations)
    return total_minutes / float(problem.rooms_available)


def _normalize_span_score(
    actual_avg: float, lower_bound: float, upper_bound: float
) -> float:
    """1.0 when actual ≤ lower_bound; 0.0 when actual ≥ upper_bound."""
    if upper_bound <= lower_bound:
        return 1.0 if actual_avg <= lower_bound else 0.0
    return _clamp01(1.0 - (actual_avg - lower_bound) / (upper_bound - lower_bound))


def score_soft_constraints(
    problem: ScheduleProblem, result: ScheduleResult, metrics: QualityMetrics
) -> SoftScores:
    pres_by_id = {p.id: p for p in problem.presentations}
    total = metrics.total_count

    # 1. scheduling_completeness
    completeness = metrics.scheduled_pct

    # If nothing was scheduled, the rest of the scores are undefined; report 0.0
    # for all of them so the aggregate reflects the failure cleanly.
    if metrics.scheduled_count == 0:
        return SoftScores(
            scheduling_completeness=completeness,
            minimize_makespan=0.0,
            minimize_dept_span=0.0,
            minimize_class_span=0.0,
            minimize_prof_span=0.0,
            balance_rooms=0.0,
            student_availability=1.0 if total == 0 else 0.0,
            aggregate_soft_score=completeness * 0.0 if total > 0 else 1.0,
        )

    horizon = _total_horizon_minutes(problem)

    # 2. minimize_makespan: lower_bound / actual, clamped 0..1.
    lb_makespan = _makespan_lower_bound_minutes(problem)
    if metrics.makespan_minutes <= 0:
        makespan_score = 1.0
    else:
        makespan_score = _clamp01(lb_makespan / metrics.makespan_minutes)

    # 3/4/5. dept/class/prof span: normalize avg actual against per-group lower bound.
    dept_lbs = list(_group_lower_bound_minutes(
        problem.presentations, lambda p: p.department_id
    ).values())
    class_lbs = list(_group_lower_bound_minutes(
        problem.presentations, lambda p: p.class_id
    ).values())

    prof_set = set(problem.professor_resource_ids)
    identity = problem.resource_identity or {}

    def prof_group_key(p: PresentationInput) -> list[str]:
        return [identity.get(rid, rid) for rid in p.resource_ids if rid in prof_set]

    prof_lbs = list(_group_lower_bound_minutes(
        problem.presentations, prof_group_key
    ).values())

    avg_lb = (
        lambda lst: (sum(lst) / len(lst)) if lst else 0.0
    )

    dept_score = _normalize_span_score(
        metrics.dept_span_avg_minutes, avg_lb(dept_lbs), horizon
    )
    class_score = _normalize_span_score(
        metrics.class_span_avg_minutes, avg_lb(class_lbs), horizon
    )
    prof_score = _normalize_span_score(
        metrics.prof_span_avg_minutes, avg_lb(prof_lbs), horizon
    )

    # 6. balance_rooms: 1 - (max-min)/sum of room minutes.
    total_assigned_minutes = sum(
        (a.end - a.start).total_seconds() / 60.0 for a in result.assignments
    )
    if total_assigned_minutes <= 0 or problem.rooms_available <= 1:
        balance_score = 1.0
    else:
        balance_score = _clamp01(
            1.0 - metrics.room_load_minutes_imbalance / total_assigned_minutes
        )

    # 7. student_availability: 1 - violations / total
    if total <= 0:
        student_score = 1.0
    else:
        student_score = _clamp01(
            1.0 - metrics.soft_availability_violations / float(total)
        )

    # Aggregate: geometric mean of the seven (with completeness weighted equally
    # but dominant in failure since it's a multiplier).
    components = [
        completeness,
        makespan_score,
        dept_score,
        class_score,
        prof_score,
        balance_score,
        student_score,
    ]
    # Geometric mean is 0 if any component is 0; offset slightly so a single
    # zero doesn't drag the entire score to 0 unless that component is the
    # primary failure (completeness == 0 already handled above).
    eps = 1e-3
    log_sum = sum(math.log(max(c, eps)) for c in components)
    aggregate = math.exp(log_sum / len(components))

    return SoftScores(
        scheduling_completeness=completeness,
        minimize_makespan=makespan_score,
        minimize_dept_span=dept_score,
        minimize_class_span=class_score,
        minimize_prof_span=prof_score,
        balance_rooms=balance_score,
        student_availability=student_score,
        aggregate_soft_score=aggregate,
    )
