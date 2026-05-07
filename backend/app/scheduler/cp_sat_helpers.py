from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import combinations as iter_combinations
from math import ceil
from typing import Any, cast

from app.utils import ensure_app_timezone

from .models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduledPresentation,
    ScheduleProblem,
    ScheduleResult,
)

logger = logging.getLogger(__name__)


def _ensure_utc(moment: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for solver comparisons."""
    if moment.tzinfo is None:
        return ensure_app_timezone(moment).astimezone(timezone.utc)
    return moment.astimezone(timezone.utc)


def _normalize_windows(
    windows: tuple[AvailabilityWindow, ...],
) -> tuple[AvailabilityWindow, ...]:
    """Drop invalid windows, normalize endpoints to UTC, and sort by start time."""
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
    """Return true when one availability window fully contains the interval."""
    return any(start >= window.start and end <= window.end for window in windows)


def _slot_count(duration_minutes: int, slot_minutes: int) -> int:
    """Convert a duration in minutes to the number of CP-SAT time slots it spans."""
    return ceil(duration_minutes / slot_minutes)


def _eligible_starts(
    presentation: PresentationInput,
    symposium_windows: tuple[AvailabilityWindow, ...],
    resource_windows: dict[str, tuple[AvailabilityWindow, ...]],
    slot_minutes: int,
    base_time: datetime | None = None,
) -> tuple[datetime, ...]:
    """Find all hard-window-valid start times for one presentation.

    Candidates are aligned to the ``base_time + N × slot_minutes`` grid that
    the solver uses internally. If ``base_time`` is omitted we fall back to
    each window's own start (matches earlier behaviour); pass it explicitly
    when the model converts datetimes back to slot indices via
    ``(t - base_time) / step`` so slot truncation can never silently shift
    a candidate before the window opens. """
    starts: list[datetime] = []
    duration = timedelta(minutes=presentation.duration_minutes)
    step = timedelta(minutes=slot_minutes)

    # A candidate is allowed only when every hard-constrained resource is also available.
    for window in symposium_windows:
        if base_time is not None:
            offset_min = (window.start - base_time).total_seconds() / 60.0
            slot_idx = max(0, ceil(offset_min / slot_minutes))
            candidate = base_time + timedelta(minutes=slot_idx * slot_minutes)
        else:
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


def _build_admin_suggestions(
    problem: ScheduleProblem,
    diagnostics: tuple[str, ...],
    unscheduled_presentations: tuple[str, ...],
) -> tuple[str, ...]:
    """Translate scheduler failures into actionable admin-facing suggestions."""
    suggestions: list[str] = []

    # Capacity checks compare total required presentation+buffer minutes against
    # the available room-minutes across all symposium windows.
    total_sym_minutes = sum(
        int((w.end - w.start).total_seconds() // 60)
        for w in problem.symposium_windows
    )
    total_room_minutes = total_sym_minutes * problem.rooms_available
    total_required_minutes = sum(
        p.duration_minutes + p.buffer_minutes for p in problem.presentations
    )

    # Extract blocked presentation titles from diagnostics 
    blocked_titles: list[str] = []
    for msg in diagnostics:
        if "could not be scheduled" in msg and msg.startswith('"'):
            end_quote = msg.index('"', 1)
            blocked_titles.append(msg[1:end_quote])

    def _title_list(titles: list[str], limit: int = 3) -> str:
        """Format a short quoted list of blocked presentation titles."""
        shown = [f'"{t}"' for t in titles[:limit]]
        rest = len(titles) - limit
        suffix = f" and {rest} more" if rest > 0 else ""
        return ", ".join(shown) + suffix

    # Suggestion: availability bottleneck 
    if blocked_titles:
        blocked_ids = set(unscheduled_presentations)
        blocked_pres = [p for p in problem.presentations if p.id in blocked_ids]
        prof_ids = set(problem.professor_resource_ids)
        has_prof = any(any(r in prof_ids for r in p.resource_ids) for p in blocked_pres)
        has_student = any(any(r not in prof_ids for r in p.resource_ids) for p in blocked_pres)

        if has_prof and has_student:
            suggestions.append(
                f"{len(blocked_titles)} presentation(s) — {_title_list(blocked_titles)} — "
                f"could not be placed because the professor's and/or student's availability "
                f"windows have no overlap with the symposium schedule. "
                f"Expand the relevant availability windows, or set 'Professor Availability' "
                f"and/or 'Student Availability' to Soft and re-run."
            )
        elif has_prof:
            suggestions.append(
                f"{len(blocked_titles)} presentation(s) — {_title_list(blocked_titles)} — "
                f"could not be placed because the professor's availability window has no overlap "
                f"with the symposium schedule. Expand the professor's availability window or set "
                f"'Professor Availability' to Soft and re-run."
            )
        else:
            suggestions.append(
                f"{len(blocked_titles)} presentation(s) — {_title_list(blocked_titles)} — "
                f"could not be placed because the student's availability window has no overlap "
                f"with the symposium schedule. Expand student availability windows or set "
                f"'Student Availability' to Soft and re-run."
            )

    # Suggestion: overloaded classes (same-class-same-room hard)
    if problem.constraints.same_class_same_room == "hard":
        class_load: dict[str, list[PresentationInput]] = defaultdict(list)
        for p in problem.presentations:
            if p.class_id:
                class_load[p.class_id].append(p)
        overloaded = [
            (presos, sum(p.duration_minutes + p.buffer_minutes for p in presos))
            for presos in class_load.values()
            if sum(p.duration_minutes + p.buffer_minutes for p in presos) > total_sym_minutes
        ]
        if overloaded:
            presos, class_total = max(overloaded, key=lambda x: x[1] - total_sym_minutes)
            shortage = class_total - total_sym_minutes
            rooms_needed = ceil(class_total / total_sym_minutes)
            extra = rooms_needed - problem.rooms_available
            sample = presos[0].title
            suggestions.append(
                f"The class containing \"{sample}\" has {len(presos)} presentations totalling "
                f"{class_total} min, but only {total_sym_minutes} min is available per room. "
                f"With 'Same Class → Same Room' set to Hard they must all share one room — "
                f"{shortage} min over the limit. Set 'Same Class \u2192 Same Room' to Soft to let "
                f"the scheduler spread this class across rooms."
            )
        elif len(class_load) > 0 and len(unscheduled_presentations) > 0:
            suggestions.append(
                f"'Same Class → Same Room' is Hard, forcing every class into a single room. "
                f"This can cause overflow even when total capacity looks sufficient. "
                f"Set it to Soft so the scheduler can spread presentations across rooms."
            )

    # Suggestion: overall capacity
    if total_required_minutes > total_room_minutes:
        shortage = total_required_minutes - total_room_minutes
        extra_rooms = ceil(total_required_minutes / total_sym_minutes) - problem.rooms_available
        room_advice = f"Adding {extra_rooms} more room(s)" if extra_rooms > 0 else "Adding more rooms"
        suggestions.append(
            f"Total required time ({total_required_minutes} min) exceeds total room capacity "
            f"({total_room_minutes} min across {problem.rooms_available} room(s)) by {shortage} min. "
            f"{room_advice} or extending the symposium window would resolve this."
        )

    # Suggestion: buffers adding significant dead time
    buffered = [p for p in problem.presentations if p.buffer_minutes > 0]
    if buffered and unscheduled_presentations:
        total_buf = sum(p.buffer_minutes for p in buffered)
        avg_buf = total_buf // len(buffered)
        suggestions.append(
            f"Room buffers account for {total_buf} min of dead time across "
            f"{len(buffered)} presentation(s) (avg {avg_buf} min each). "
            f"Reducing buffer sizes in the presentation editor would free {total_buf} min of room time."
        )

    if not suggestions:
        suggestions.append(
            "Try switching constraints from Hard to Soft one at a time and re-running after each "
            "change to isolate which rule is causing the failure."
        )

    return tuple(suggestions)


def _run_exhaustive_debug(
    problem: ScheduleProblem,
    current_unscheduled: int,
    total_time_budget: float = 540.0,
) -> tuple[tuple[str, ...], tuple[ScheduledPresentation, ...]]:
    """Try every combination of relaxing hard constraints in parallel to find the
    configuration that schedules the most presentations.

    All combos run concurrently in a thread pool.  CP-SAT releases the GIL so
    threads genuinely run in parallel.  Each flat probe uses num_search_workers=1
    to avoid CPU thrashing.  Hierarchical probes run CP-SAT at default parallelism
    inside place_blocks, so we cap thread-pool fan-out lower for that path.

    The best result is chosen by (1) fewest unscheduled, then (2) fewest
    relaxations (prefer the minimal constraint change).
    """

    if current_unscheduled == 0:
        return (), ()

    # Deferred import to avoid the circular service ↔ cp_sat_helpers cycle.
    from .service import _should_use_hierarchical, build_problem_from_symposium

    # Only hard constraints are candidates for relaxation. Each probe turns one
    # or more of them soft and re-runs the normal solver on that variant.
    relaxable: list[tuple[str, str]] = [
        ("professor_availability", "professor availability"),
        ("student_availability", "student availability"),
        ("same_class_same_room", "same class → same room"),
        ("room_conflicts", "room conflicts"),
        ("person_conflicts", "person conflicts"),
    ]

    hard_constraints = [
        (attr, label) for attr, label in relaxable
        if getattr(problem.constraints, attr) == "hard"
    ]

    if not hard_constraints:
        return ("[Debugger] No hard constraints to relax — try adding more rooms or extending the symposium window.",), ()

    n = len(hard_constraints)
    n_combos = 2 ** n - 1  # exclude the all-hard case already run

    use_hierarchical = _should_use_hierarchical(problem)

    # Hierarchical probes run the full phase 1+2+3+5 pipeline with default
    # CP-SAT parallelism, so each probe needs more wall time and fewer of them
    # should run concurrently to avoid CPU oversubscription. Flat probes are
    # lighter (single CP-SAT model, num_search_workers=1) so we keep the
    # original budget.
    if use_hierarchical:
        # Each hierarchical probe runs CP-SAT with num_search_workers=1 to
        # contain RAM, so it converges 3–4× slower than a default-parallelism
        # solve. Compensate by giving each probe more wall time.
        time_per_probe = max(40.0, min(90.0, total_time_budget / n_combos))
    else:
        time_per_probe = max(10.0, min(30.0, total_time_budget / n_combos))

    # Build all combos ordered by number of relaxations (fewest first) so that
    # when we pick among equally-good results we favour the minimal change.
    all_combos: list[dict[str, str]] = []
    for r in range(1, n + 1):
        for subset in iter_combinations(range(n), r):
            all_combos.append({hard_constraints[i][0]: "soft" for i in subset})

    total_presentations = len(problem.presentations)

    def _probe(relaxed_attrs: dict[str, str]) -> tuple[dict[str, str], ScheduleResult]:
        """Run one solver probe with a selected set of hard constraints relaxed.

        We rebuild the problem from the symposium id rather than using
        dataclasses.replace on the existing problem because hard prof/student
        windows are split into resource_windows vs soft_resource_windows during
        problem construction, and hierarchical phase 1 bakes the hard windows
        into block formation. Re-bucketing inline would duplicate that logic.
        """
        relaxed_constraints = replace(problem.constraints, **cast(Any, relaxed_attrs))
        try:
            relaxed_problem = build_problem_from_symposium(
                symposium_id=problem.symposium_id,
                slot_minutes=problem.slot_minutes,
                constraints=relaxed_constraints,
            )
            if _should_use_hierarchical(relaxed_problem):
                from .hierarchical import solve_hierarchical

                result = solve_hierarchical(
                    relaxed_problem,
                    time_limit_seconds=time_per_probe,
                    num_search_workers=1,
                )
            else:
                from .cp_sat import solve_schedule

                result = solve_schedule(relaxed_problem, time_limit_seconds=time_per_probe, num_search_workers=1)
            return relaxed_attrs, result
        except Exception:
            logger.debug("Exhaustive probe failed for %s", relaxed_attrs, exc_info=True)
            return relaxed_attrs, ScheduleResult(
                status="infeasible",
                assignments=(),
                unscheduled_presentations=tuple(p.id for p in problem.presentations),
            )

    # Cap concurrency. Flat probes are tiny — 8 wide is fine. Hierarchical
    # probes each rebuild the full ScheduleProblem and run a multi-phase
    # CP-SAT pipeline; even with num_search_workers=1, two probes in flight
    # still cap RAM at roughly 2× a single hierarchical solve. A previous run
    # with cap=4 + default 4-worker CP-SAT inside place_blocks ate ~17 GB on
    # a 102-presentation symposium and OOM-killed the worker.
    parallel_cap = 2 if use_hierarchical else 8
    max_workers = min(n_combos, parallel_cap)
    probe_results: list[tuple[dict[str, str], ScheduleResult]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_probe, combo): combo for combo in all_combos}
        for future in as_completed(futures):
            probe_results.append(future.result())

    # Pick the best result: fewest unscheduled, then fewest relaxations.
    probe_results.sort(key=lambda x: (len(x[1].unscheduled_presentations), len(x[0])))
    best_relaxations, best_result = probe_results[0]
    best_unscheduled = len(best_result.unscheduled_presentations)

    if best_unscheduled >= current_unscheduled:
        return (
            "[Debugger] No constraint combination improved scheduling. "
            "The bottleneck is likely capacity — try adding rooms or extending the symposium window.",
        ), ()

    hints: list[str] = []
    improvement = current_unscheduled - best_unscheduled

    if best_unscheduled == 0:
        hints.append(
            f"[Debugger] A fully optimal configuration was found: all {total_presentations} "
            f"presentations can be scheduled with the settings below."
        )
    else:
        hints.append(
            f"[Debugger] Best configuration found schedules "
            f"{total_presentations - best_unscheduled}/{total_presentations} presentations "
            f"({improvement} more than current settings). Accept below to apply this schedule."
        )

    for attr, label in relaxable:
        if attr in best_relaxations:
            hints.append(f"[Debugger] Set {label} to Soft.")

    return tuple(hints), best_result.assignments
