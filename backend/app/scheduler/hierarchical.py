"""Hierarchical scheduler for very large symposia.

The flat CP-SAT solver in :mod:`app.scheduler.cp_sat` builds an O(presentations
× eligible_starts × rooms) boolean model that becomes intractable for
~300+ presentation symposia. This module decomposes the problem along the
natural seam in the data model: each professor and each student belongs to
exactly one class, so classes have disjoint people. The only cross-class
coupling is rooms and the symposium window — until you account for the same
person being entered into multiple classes (double-major students, cross-
listed faculty), which we handle via an email-keyed identity map.

Pipeline:

* **Phase 1 — `prepare_class_blocks`**: bundle each class's presentations into
  one or more contiguous "blocks" (sub-blocks if the class doesn't fit in a
  single contiguous symposium window).
* **Phase 2 — `place_blocks`**: small CP-SAT model that picks (room, start) per
  block. Constraints: room no-overlap, cross-block identity no-overlap, same-
  class-same-room. Optional unscheduled blocks with heavy penalty.
* **Phase 3 — `expand_blocks`**: deterministic per-block layout that emits one
  `ScheduledPresentation` per presentation, sequentially.
* **Phase 5 — `verify_assignments`**: full pairwise sweep over the generated
  schedule using identity-based personhood. Catches any subtle off-by-one
  in the decomposition before save. (Phase 4 is the cross-block constraint
  built into phase 2; the verification sweep is the belt-and-braces check.)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil
from ortools.sat.python import cp_model

from app.scheduler.models import (
    AvailabilityWindow,
    ClassBlock,
    PlacedBlock,
    PresentationInput,
    ScheduleProblem,
    ScheduleResult,
    ScheduledPresentation,
)

logger = logging.getLogger(__name__)


# ── Window utilities ────────────────────────────────────────────────────────


def _ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _normalize(windows: tuple[AvailabilityWindow, ...]) -> tuple[AvailabilityWindow, ...]:
    """Sort + merge overlapping windows; drop zero-length."""
    cleaned = sorted(
        (
            AvailabilityWindow(start=_ensure_utc(w.start), end=_ensure_utc(w.end))
            for w in windows
            if w.end > w.start
        ),
        key=lambda w: w.start,
    )
    if not cleaned:
        return ()
    merged: list[AvailabilityWindow] = [cleaned[0]]
    for w in cleaned[1:]:
        last = merged[-1]
        if w.start <= last.end:
            merged[-1] = AvailabilityWindow(start=last.start, end=max(last.end, w.end))
        else:
            merged.append(w)
    return tuple(merged)


def _intersect_two(
    a: tuple[AvailabilityWindow, ...], b: tuple[AvailabilityWindow, ...]
) -> tuple[AvailabilityWindow, ...]:
    out: list[AvailabilityWindow] = []
    i = j = 0
    while i < len(a) and j < len(b):
        wa, wb = a[i], b[j]
        start = max(wa.start, wb.start)
        end = min(wa.end, wb.end)
        if end > start:
            out.append(AvailabilityWindow(start=start, end=end))
        if wa.end < wb.end:
            i += 1
        else:
            j += 1
    return tuple(out)


def _intersect_all(
    windows_list: list[tuple[AvailabilityWindow, ...]],
) -> tuple[AvailabilityWindow, ...]:
    if not windows_list:
        return ()
    result = _normalize(windows_list[0])
    for w in windows_list[1:]:
        result = _intersect_two(result, _normalize(w))
        if not result:
            return ()
    return result


# ── Phase 1: build class blocks ─────────────────────────────────────────────


def _identity_for(rid: str, problem: ScheduleProblem) -> str:
    return problem.resource_identity.get(rid, rid)


def _block_resource_identities(
    presentations: list[PresentationInput], problem: ScheduleProblem
) -> frozenset[str]:
    idents: set[str] = set()
    for p in presentations:
        for rid in p.resource_ids:
            idents.add(_identity_for(rid, problem))
    return frozenset(idents)


def _split_presentations_into_subblocks(
    presentations: list[PresentationInput],
    allowed_windows: tuple[AvailabilityWindow, ...],
    slot_minutes: int,
) -> list[list[PresentationInput]]:
    """Greedily split a class's presentations into sub-blocks that each fit in
    one contiguous allowed window.

    Strategy: iterate windows from largest to smallest, fill each with as many
    presentations as fit (in input order), move to the next window with the
    leftover. Per the user's decision, sub-blocks of the same class will be
    constrained to share a room in phase 2 — so if a window can't be used at
    all (because phase 2 will reject room-disjoint placements), the leftover
    just stays unscheduled and the verification sweep flags it.
    """
    if not presentations:
        return []

    sorted_windows = sorted(
        allowed_windows,
        key=lambda w: (w.end - w.start).total_seconds(),
        reverse=True,
    )

    subblocks: list[list[PresentationInput]] = []
    remaining = list(presentations)

    for window in sorted_windows:
        if not remaining:
            break
        capacity = (window.end - window.start).total_seconds() / 60.0
        bucket: list[PresentationInput] = []
        used = 0.0
        while remaining and used + remaining[0].duration_minutes + remaining[0].buffer_minutes <= capacity:
            p = remaining.pop(0)
            bucket.append(p)
            used += p.duration_minutes + p.buffer_minutes
        if bucket:
            subblocks.append(bucket)

    if remaining:
        # Couldn't fit; emit one final sub-block holding the leftovers so that
        # phase-2 marks it unscheduled (it will have no eligible starts).
        subblocks.append(remaining)

    return subblocks


def prepare_class_blocks(problem: ScheduleProblem) -> list[ClassBlock]:
    """Phase 1: turn a class's presentations into one or more atomic blocks."""
    by_class: dict[str, list[PresentationInput]] = defaultdict(list)
    for p in problem.presentations:
        by_class[p.class_id or p.id].append(p)

    sym_windows = _normalize(problem.symposium_windows)

    blocks: list[ClassBlock] = []
    for class_id, presentations in by_class.items():
        # Allowed window for this class = symposium ∩ (all class-prof hard windows).
        # Student windows are deliberately not intersected here — per the user's
        # decision they're handled inside the block, not at block placement.
        prof_windows: list[tuple[AvailabilityWindow, ...]] = [sym_windows]
        seen_profs: set[str] = set()
        for p in presentations:
            for rid in p.resource_ids:
                if rid in seen_profs:
                    continue
                if rid not in problem.professor_resource_ids:
                    continue
                seen_profs.add(rid)
                if rid in problem.resource_windows:
                    prof_windows.append(problem.resource_windows[rid])
        allowed = _intersect_all(prof_windows)
        if not allowed:
            # No window where every class-professor is available. Fall back to
            # symposium windows; phase-5 sweep will surface the violation.
            allowed = sym_windows

        total_minutes = sum(p.duration_minutes + p.buffer_minutes for p in presentations)
        longest_window_minutes = max(
            ((w.end - w.start).total_seconds() / 60.0 for w in allowed), default=0.0
        )

        if total_minutes <= longest_window_minutes:
            # Single block — typical case.
            blocks.append(
                ClassBlock(
                    id=f"{class_id}::0",
                    class_id=class_id,
                    presentation_ids=tuple(p.id for p in presentations),
                    total_minutes=total_minutes,
                    allowed_windows=allowed,
                    resource_identities=_block_resource_identities(presentations, problem),
                )
            )
            continue

        # Oversize — split into sub-blocks tagged with the same class_id.
        subblocks = _split_presentations_into_subblocks(presentations, allowed, problem.slot_minutes)
        for idx, group in enumerate(subblocks):
            sub_total = sum(p.duration_minutes + p.buffer_minutes for p in group)
            blocks.append(
                ClassBlock(
                    id=f"{class_id}::{idx}",
                    class_id=class_id,
                    presentation_ids=tuple(p.id for p in group),
                    total_minutes=sub_total,
                    allowed_windows=allowed,
                    resource_identities=_block_resource_identities(group, problem),
                )
            )
    return blocks


# ── Phase 2: place blocks via small CP-SAT ──────────────────────────────────


def _enumerate_block_starts(
    block: ClassBlock, base_time: datetime, slot_minutes: int
) -> list[int]:
    """Slot indices where this block can start such that it fits inside one
    contiguous allowed window.
    """
    duration = timedelta(minutes=block.total_minutes)
    step = timedelta(minutes=slot_minutes)
    starts: list[int] = []
    for window in block.allowed_windows:
        candidate = window.start
        while candidate + duration <= window.end:
            slot = int((candidate - base_time).total_seconds() / 60 / slot_minutes)
            starts.append(slot)
            candidate += step
    return starts


def place_blocks(
    blocks: list[ClassBlock], problem: ScheduleProblem, time_limit_seconds: float
) -> tuple[list[PlacedBlock], list[ClassBlock], str]:
    """Phase 2: assign each block to a (room, start_slot) using CP-SAT.

    Returns (placed_blocks, unscheduled_blocks, status_label).
    Status is "optimal", "feasible", or "infeasible".
    """
    if not blocks:
        return [], [], "optimal"

    sym_windows = _normalize(problem.symposium_windows)
    base_time = min(w.start for w in sym_windows)
    slot_minutes = max(1, problem.slot_minutes)
    horizon_slots = max(
        int((w.end - base_time).total_seconds() / 60 / slot_minutes) for w in sym_windows
    )

    block_starts: dict[str, list[int]] = {
        b.id: _enumerate_block_starts(b, base_time, slot_minutes) for b in blocks
    }
    block_duration_slots: dict[str, int] = {
        b.id: max(1, ceil(b.total_minutes / slot_minutes)) for b in blocks
    }

    schedulable = [b for b in blocks if block_starts[b.id]]
    pre_unscheduled = [b for b in blocks if not block_starts[b.id]]

    if not schedulable:
        return [], list(blocks), "infeasible"

    rooms = problem.rooms_available

    model = cp_model.CpModel()

    # assign[(block_id, start_slot, room)] = 1 iff the block is placed there
    assign: dict[tuple[str, int, int], cp_model.IntVar] = {}
    is_scheduled: dict[str, cp_model.IntVar] = {}

    for block in schedulable:
        per_block_vars: list[cp_model.IntVar] = []
        for s in block_starts[block.id]:
            for r in range(rooms):
                v = model.NewBoolVar(f"a_{block.id[:16]}_{s}_{r}")
                assign[(block.id, s, r)] = v
                per_block_vars.append(v)
        sched = model.NewBoolVar(f"sched_{block.id[:16]}")
        is_scheduled[block.id] = sched
        model.Add(sum(per_block_vars) == sched)

    # Per-room no-overlap (hard).
    for r in range(rooms):
        intervals: list[cp_model.IntervalVar] = []
        for block in schedulable:
            dur = block_duration_slots[block.id]
            for s in block_starts[block.id]:
                v = assign[(block.id, s, r)]
                iv = model.NewOptionalFixedSizeIntervalVar(
                    s, dur, v, f"riv_{block.id[:8]}_{s}_{r}"
                )
                intervals.append(iv)
        if intervals:
            model.AddNoOverlap(intervals)

    # Cross-block person conflicts: any two blocks that share a person identity
    # cannot run at the same time, regardless of room. Catches double-major
    # students and cross-listed professors that would otherwise slip through
    # the per-class decomposition.
    blocks_by_identity: dict[str, list[ClassBlock]] = defaultdict(list)
    for block in schedulable:
        for ident in block.resource_identities:
            blocks_by_identity[ident].append(block)

    for ident, ident_blocks in blocks_by_identity.items():
        if len(ident_blocks) < 2:
            continue
        intervals_p: list[cp_model.IntervalVar] = []
        for block in ident_blocks:
            dur = block_duration_slots[block.id]
            for s in block_starts[block.id]:
                room_vars = [assign[(block.id, s, r)] for r in range(rooms)]
                if rooms == 1:
                    active: cp_model.IntVar = room_vars[0]
                else:
                    active = model.NewBoolVar(f"act_{block.id[:8]}_{s}")
                    model.Add(sum(room_vars) == active)
                iv = model.NewOptionalFixedSizeIntervalVar(
                    s, dur, active, f"piv_{ident[:6]}_{block.id[:8]}_{s}"
                )
                intervals_p.append(iv)
        if len(intervals_p) > 1:
            model.AddNoOverlap(intervals_p)

    # Same-class-same-room: all sub-blocks of one class share a single room.
    if problem.constraints.same_class_same_room == "hard":
        blocks_by_class: dict[str, list[ClassBlock]] = defaultdict(list)
        for block in schedulable:
            blocks_by_class[block.class_id].append(block)
        for class_id, class_blocks in blocks_by_class.items():
            if len(class_blocks) < 2:
                continue
            class_room = model.NewIntVar(0, rooms - 1, f"cr_{class_id[:12]}")
            for block in class_blocks:
                for s in block_starts[block.id]:
                    for r in range(rooms):
                        v = assign[(block.id, s, r)]
                        model.Add(class_room == r).OnlyEnforceIf(v)

    # Objective: maximize scheduled blocks (heavily) then minimize makespan.
    end_slot_per_block: list[cp_model.IntVar] = []
    for block in schedulable:
        end = model.NewIntVar(0, horizon_slots, f"end_{block.id[:12]}")
        dur = block_duration_slots[block.id]
        model.Add(
            end
            == sum(
                (s + dur) * assign[(block.id, s, r)]
                for s in block_starts[block.id]
                for r in range(rooms)
            )
        )
        end_slot_per_block.append(end)

    makespan = model.NewIntVar(0, horizon_slots, "makespan")
    if end_slot_per_block:
        model.AddMaxEquality(makespan, end_slot_per_block)

    unscheduled_count = len(schedulable) - sum(is_scheduled.values())
    # Unscheduling a block must always cost more than any makespan reduction.
    # horizon_slots × 1 is the worst-case makespan weight; len(schedulable) ×
    # horizon_slots is a comfortable upper bound on the penalty.
    unscheduled_penalty = max(1, horizon_slots) * (len(schedulable) + 1)
    model.Minimize(unscheduled_count * unscheduled_penalty + makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 4

    t0 = time.perf_counter()
    status = solver.Solve(model)
    logger.info(
        "place_blocks: blocks=%d  status=%s  wall=%.2fs",
        len(schedulable), solver.StatusName(status), time.perf_counter() - t0,
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], list(blocks), "infeasible"

    placed: list[PlacedBlock] = []
    cp_unscheduled: list[ClassBlock] = list(pre_unscheduled)
    for block in schedulable:
        if solver.Value(is_scheduled[block.id]) == 0:
            cp_unscheduled.append(block)
            continue
        for s in block_starts[block.id]:
            for r in range(rooms):
                if solver.Value(assign[(block.id, s, r)]) == 1:
                    start = base_time + timedelta(minutes=s * slot_minutes)
                    placed.append(PlacedBlock(block=block, room_index=r, start=start))
                    break

    label = "optimal" if status == cp_model.OPTIMAL else "feasible"
    return placed, cp_unscheduled, label


# ── Phase 3: deterministic per-block expansion ──────────────────────────────


def expand_blocks(
    placed: list[PlacedBlock], problem: ScheduleProblem
) -> tuple[ScheduledPresentation, ...]:
    presentation_by_id: dict[str, PresentationInput] = {p.id: p for p in problem.presentations}
    out: list[ScheduledPresentation] = []
    for pb in placed:
        cursor = _ensure_utc(pb.start)
        for pid in pb.block.presentation_ids:
            p = presentation_by_id[pid]
            end = cursor + timedelta(minutes=p.duration_minutes)
            out.append(
                ScheduledPresentation(
                    presentation_id=pid,
                    room_index=pb.room_index,
                    start=cursor,
                    end=end,
                )
            )
            cursor = end + timedelta(minutes=p.buffer_minutes)
    out.sort(key=lambda a: (a.start, a.room_index, a.presentation_id))
    return tuple(out)


# ── Phase 5: verification sweep ────────────────────────────────────────────


def verify_assignments(
    assignments: tuple[ScheduledPresentation, ...], problem: ScheduleProblem
) -> tuple[str, ...]:
    """Backwards-compatible wrapper: returns *only* hard structural issues
    (room/person/symposium-window conflicts).

    Resource-window violations (a student or professor scheduled outside their
    availability window) are surfaced separately by ``verify_assignments_split``
    so callers can decide whether they should fail the schedule or just warn.
    """
    hard, _soft = verify_assignments_split(assignments, problem)
    return hard


def verify_assignments_split(
    assignments: tuple[ScheduledPresentation, ...], problem: ScheduleProblem
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Audit the schedule, returning ``(hard_issues, soft_warnings)``.

    Hard issues mean the schedule is structurally broken — saving it would put
    two presentations in one room, double-book a person, or place a talk
    outside the symposium. Callers should refuse to save in that case.

    Soft warnings are per-resource availability misses (a student or professor
    scheduled outside their stated window). These do not break the schedule
    structurally; the hierarchical path expects to see some of these because
    its design decision is to place blocks based on professor + symposium
    windows and surface student misses as warnings rather than fail.
    """
    hard_issues: list[str] = []
    soft_issues: list[str] = []
    pres_by_id: dict[str, PresentationInput] = {p.id: p for p in problem.presentations}

    sym_windows = _normalize(problem.symposium_windows)

    pres_identities: dict[str, set[str]] = {}
    for p in problem.presentations:
        idents: set[str] = set()
        for rid in p.resource_ids:
            idents.add(_identity_for(rid, problem))
        pres_identities[p.id] = idents

    def _name_for_identity(identity: str) -> str:
        # Find any resource_id pointing at this identity and use its name.
        for rid, ident in problem.resource_identity.items():
            if ident == identity and rid in problem.resource_name:
                return problem.resource_name[rid]
        return identity

    # Single-assignment checks.
    for a in assignments:
        a_start = _ensure_utc(a.start)
        a_end = _ensure_utc(a.end)
        title = pres_by_id[a.presentation_id].title if a.presentation_id in pres_by_id else a.presentation_id
        if not any(a_start >= w.start and a_end <= w.end for w in sym_windows):
            hard_issues.append(
                f'Schedule integrity: "{title}" lands outside the symposium windows.'
            )
        pres = pres_by_id.get(a.presentation_id)
        if pres is None:
            continue
        for rid in pres.resource_ids:
            if rid not in problem.resource_windows:
                continue
            windows = _normalize(problem.resource_windows[rid])
            if not windows:
                continue
            if not any(a_start >= w.start and a_end <= w.end for w in windows):
                name = problem.resource_name.get(rid, "Someone")
                soft_issues.append(
                    f'Availability warning: "{title}" runs outside {name}\'s availability window.'
                )

    # Pairwise checks.
    n = len(assignments)
    for i in range(n):
        a = assignments[i]
        a_start = _ensure_utc(a.start)
        a_end = _ensure_utc(a.end)
        title_a = pres_by_id[a.presentation_id].title if a.presentation_id in pres_by_id else a.presentation_id
        for j in range(i + 1, n):
            b = assignments[j]
            b_start = _ensure_utc(b.start)
            b_end = _ensure_utc(b.end)
            if not (a_start < b_end and b_start < a_end):
                continue
            title_b = pres_by_id[b.presentation_id].title if b.presentation_id in pres_by_id else b.presentation_id
            if a.room_index == b.room_index:
                hard_issues.append(
                    f'Schedule integrity: room {a.room_index + 1} is double-booked '
                    f'between "{title_a}" and "{title_b}".'
                )
            shared = pres_identities.get(a.presentation_id, set()) & pres_identities.get(b.presentation_id, set())
            if shared:
                ident = next(iter(shared))
                name = _name_for_identity(ident)
                hard_issues.append(
                    f'Schedule integrity: "{name}" is required at both "{title_a}" and '
                    f'"{title_b}" at the same time.'
                )
    return tuple(hard_issues), tuple(soft_issues)


# ── Top-level entry point ──────────────────────────────────────────────────


def solve_hierarchical(
    problem: ScheduleProblem, time_limit_seconds: float = 30.0
) -> ScheduleResult:
    """Run the full pipeline end-to-end and return a ScheduleResult."""
    t_total = time.perf_counter()

    if not problem.symposium_windows:
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=("No symposium availability windows were provided.",),
        )
    if not problem.presentations:
        return ScheduleResult(status="optimal", assignments=())

    blocks = prepare_class_blocks(problem)
    logger.info(
        "hierarchical: built %d class block(s) from %d presentation(s)",
        len(blocks), len(problem.presentations),
    )

    placed, unscheduled_blocks, status_label = place_blocks(
        blocks, problem, time_limit_seconds
    )

    if status_label == "infeasible":
        return ScheduleResult(
            status="infeasible",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=(
                "Hierarchical scheduler could not find a feasible block placement.",
            ),
            suggestions=(
                "Add more rooms or extend the symposium window. "
                f"{len(blocks)} class block(s) totalling "
                f"{sum(b.total_minutes for b in blocks)} minutes need to fit.",
            ),
        )

    assignments = expand_blocks(placed, problem)

    hard_issues, soft_warnings = verify_assignments_split(assignments, problem)
    if hard_issues:
        logger.error("hierarchical verification sweep found %d hard issue(s)", len(hard_issues))
        return ScheduleResult(
            status="invalid",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=tuple(hard_issues),
            suggestions=(
                "The hierarchical scheduler emitted a schedule that fails its own "
                "verification sweep. This is a bug — please report the symposium id.",
            ),
        )
    logger.info(
        "hierarchical verification sweep: %d soft availability warning(s), 0 hard issues",
        len(soft_warnings),
    )

    unscheduled_pres: list[str] = []
    for block in unscheduled_blocks:
        unscheduled_pres.extend(block.presentation_ids)

    diagnostics: list[str] = []
    if unscheduled_pres:
        diagnostics.append(
            f"{len(unscheduled_pres)} presentation(s) across "
            f"{len(unscheduled_blocks)} class block(s) could not be placed."
        )
    # Soft warnings (e.g. a student scheduled outside their stated window) are
    # passed through as diagnostics — the schedule is structurally sound, but
    # the admin should review these and either adjust the student's window or
    # manually move the slot.
    if soft_warnings:
        diagnostics.append(
            f"{len(soft_warnings)} availability warning(s) — at least one presenter "
            f"is scheduled outside their stated availability window. The schedule "
            f"is structurally valid but you may want to manually move these slots."
        )
        # Cap the per-warning text we emit so we don't bloat the response.
        max_warnings_to_show = 25
        diagnostics.extend(soft_warnings[:max_warnings_to_show])
        if len(soft_warnings) > max_warnings_to_show:
            diagnostics.append(
                f"… and {len(soft_warnings) - max_warnings_to_show} more availability warning(s)."
            )

    logger.info(
        "hierarchical complete: scheduled=%d unscheduled=%d wall=%.2fs",
        len(assignments), len(unscheduled_pres), time.perf_counter() - t_total,
    )

    return ScheduleResult(
        status=status_label,
        assignments=assignments,
        unscheduled_presentations=tuple(unscheduled_pres),
        diagnostics=tuple(diagnostics),
    )
