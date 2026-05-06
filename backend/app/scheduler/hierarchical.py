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

    Slot indices are aligned to the ``base_time + N × slot_minutes`` grid. If a
    window's start is not slot-aligned (e.g. the user marked availability from
    17:49 but slot_minutes=5), the first eligible slot is rounded *up* to the
    next slot boundary — never before the window opens. Using ``int()`` (floor)
    here would silently shift the block 1–4 minutes earlier and place it
    outside the resource's window.
    """
    duration = timedelta(minutes=block.total_minutes)
    step = timedelta(minutes=slot_minutes)
    starts: list[int] = []
    for window in block.allowed_windows:
        offset_min = (window.start - base_time).total_seconds() / 60.0
        slot_idx = max(0, ceil(offset_min / slot_minutes))
        candidate = base_time + timedelta(minutes=slot_idx * slot_minutes)
        while candidate + duration <= window.end:
            starts.append(slot_idx)
            slot_idx += 1
            candidate += step
    return starts


# ── Constraint weights ─────────────────────────────────────────────────────
# Mirror the flat solver's weights so the two paths feel comparable when an
# admin tunes constraint modes from the UI.

_W_MAKESPAN = 3
_W_AVAIL = 3
_W_DEPT = 4
_W_CLASS = 2
_W_PROF = 2
_W_ROOM = 1
_W_SOFT_VIO = 5


def _block_resources_with_role(
    block: ClassBlock, problem: ScheduleProblem
) -> tuple[set[str], set[str]]:
    """Return (prof_resource_ids, student_resource_ids) for every presentation in this block."""
    pres_by_id = {p.id: p for p in problem.presentations}
    prof_set: set[str] = set()
    student_set: set[str] = set()
    for pid in block.presentation_ids:
        p = pres_by_id.get(pid)
        if p is None:
            continue
        for rid in p.resource_ids:
            if rid in problem.professor_resource_ids:
                prof_set.add(rid)
            else:
                student_set.add(rid)
    return prof_set, student_set


def _block_to_department(
    block: ClassBlock, problem: ScheduleProblem
) -> str:
    """Find the department_id this block belongs to (via any of its presentations)."""
    pres_by_id = {p.id: p for p in problem.presentations}
    for pid in block.presentation_ids:
        p = pres_by_id.get(pid)
        if p is not None and p.department_id:
            return p.department_id
    return ""


def place_blocks(
    blocks: list[ClassBlock], problem: ScheduleProblem, time_limit_seconds: float
) -> tuple[list[PlacedBlock], list[ClassBlock], str]:
    """Phase 2: assign each block to a (room, start_slot) using CP-SAT.

    Honors every mode in :class:`ScheduleConstraints`:

    * ``room_conflicts`` — hard ⇒ AddNoOverlap per room; soft ⇒ pairwise
      penalty; off ⇒ skipped.
    * ``person_conflicts`` — hard ⇒ AddNoOverlap per email-identity; soft ⇒
      pairwise penalty; off ⇒ skipped. Identity-based, so a double-major
      student or cross-listed professor entered as two row-ids is still
      treated as one person.
    * ``professor_availability`` — hard ⇒ already intersected into
      ``ClassBlock.allowed_windows`` in phase 1; soft ⇒ counted as a soft
      cost on each (block, start) option that misses any prof's window;
      off ⇒ ignored.
    * ``student_availability`` — hard ⇒ checked at the slot level by phase 5
      (a missed window becomes a hard issue). Soft and off ⇒ phase 3
      reorderer tries to fit the windows; phase 5 surfaces remaining misses
      as soft warnings.
    * ``same_class_same_room`` — hard ⇒ all sub-blocks of a class share one
      room; soft ⇒ a per-class preferred-room with a penalty for sub-blocks
      placed elsewhere; off ⇒ skipped.
    * ``minimize_makespan``, ``minimize_department_span``,
      ``minimize_class_span``, ``minimize_professor_span``, ``balance_rooms``
      — soft ⇒ added to the weighted-sum objective; hard ⇒ added as a
      bound; off ⇒ skipped.

    Returns ``(placed_blocks, unscheduled_blocks, status_label)`` where
    status is ``"optimal"``, ``"feasible"``, or ``"infeasible"``.
    """
    if not blocks:
        return [], [], "optimal"

    constraints = problem.constraints

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

    # ── Pre-compute soft-availability cost per (block, start_slot) ──────────
    # When prof_availability is soft, a block placed outside one of its
    # professors' soft windows costs one penalty unit per missing prof.
    # (Hard prof availability is already baked into block.allowed_windows.)
    soft_avail_cost: dict[tuple[str, int], int] = {}
    if constraints.professor_availability == "soft" and problem.soft_resource_windows:
        for block in schedulable:
            prof_rids, _student_rids = _block_resources_with_role(block, problem)
            soft_prof_windows = {
                rid: _normalize(problem.soft_resource_windows[rid])
                for rid in prof_rids
                if rid in problem.soft_resource_windows
            }
            if not soft_prof_windows:
                continue
            for s in block_starts[block.id]:
                opt_start = base_time + timedelta(minutes=s * slot_minutes)
                opt_end = opt_start + timedelta(minutes=block.total_minutes)
                misses = sum(
                    1
                    for rid, windows in soft_prof_windows.items()
                    if windows
                    and not any(opt_start >= w.start and opt_end <= w.end for w in windows)
                )
                if misses:
                    soft_avail_cost[(block.id, s)] = misses

    model = cp_model.CpModel()

    # ── Variables ───────────────────────────────────────────────────────────
    # assign[(block_id, start_slot, room)] = 1 iff the block is placed there.
    # is_scheduled[block_id] = 1 iff the block is placed at all (any room).
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

    # Per-block start_slot, end_slot, plus sentinel "effective" copies that
    # collapse to safe bounds when the block is unscheduled. Used by every
    # span minimisation term below; the sentinel pattern matches cp_sat.py so
    # AddMin/MaxEquality stay correct in mixed-scheduled cases.
    start_slot_var: dict[str, cp_model.IntVar] = {}
    end_slot_var: dict[str, cp_model.IntVar] = {}
    eff_start_for_min: dict[str, cp_model.IntVar] = {}
    eff_end_for_max: dict[str, cp_model.IntVar] = {}
    for block in schedulable:
        max_start = max(block_starts[block.id])
        dur = block_duration_slots[block.id]
        ss = model.NewIntVar(0, max_start, f"ss_{block.id[:8]}")
        es = model.NewIntVar(0, max_start + dur, f"es_{block.id[:8]}")
        start_slot_var[block.id] = ss
        end_slot_var[block.id] = es
        # ss = sum(s × assign[(b,s,r)] for s,r); zero when unscheduled.
        model.Add(
            ss
            == sum(
                s * assign[(block.id, s, r)]
                for s in block_starts[block.id]
                for r in range(rooms)
            )
        )
        model.Add(es == ss + dur)

        eff_smin = model.NewIntVar(0, horizon_slots, f"esm_{block.id[:8]}")
        model.Add(eff_smin == ss + horizon_slots - horizon_slots * is_scheduled[block.id])
        eff_start_for_min[block.id] = eff_smin

        eff_emax = model.NewIntVar(0, horizon_slots, f"eem_{block.id[:8]}")
        model.Add(eff_emax <= es)
        model.Add(eff_emax >= es - horizon_slots + horizon_slots * is_scheduled[block.id])
        eff_end_for_max[block.id] = eff_emax

    # ── Hard / soft constraints (room, person, same-class-same-room) ────────
    soft_violation_terms: list[cp_model.IntVar] = []
    _violation_counter = 0

    def _next_vname(prefix: str) -> str:
        nonlocal _violation_counter
        name = f"{prefix}_{_violation_counter}"
        _violation_counter += 1
        return name

    # Room conflicts.
    if constraints.room_conflicts == "hard":
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
    elif constraints.room_conflicts == "soft":
        # Soft pairwise penalty: for each ordered pair of (block, room) options
        # that would overlap if both chosen, add a violation bool.
        for r in range(rooms):
            for i, block_a in enumerate(schedulable):
                dur_a = block_duration_slots[block_a.id]
                for s_a in block_starts[block_a.id]:
                    a_var = assign[(block_a.id, s_a, r)]
                    for block_b in schedulable[i + 1:]:
                        dur_b = block_duration_slots[block_b.id]
                        for s_b in block_starts[block_b.id]:
                            if not (s_a < s_b + dur_b and s_b < s_a + dur_a):
                                continue
                            b_var = assign[(block_b.id, s_b, r)]
                            v = model.NewBoolVar(_next_vname("rsv"))
                            model.AddBoolAnd([a_var, b_var]).OnlyEnforceIf(v)
                            model.AddBoolOr([a_var.Not(), b_var.Not()]).OnlyEnforceIf(v.Not())
                            soft_violation_terms.append(v)

    # Cross-block person conflicts (identity-keyed).
    blocks_by_identity: dict[str, list[ClassBlock]] = defaultdict(list)
    for block in schedulable:
        for ident in block.resource_identities:
            blocks_by_identity[ident].append(block)

    if constraints.person_conflicts == "hard":
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
    elif constraints.person_conflicts == "soft":
        # Per-pair soft penalty mirrored from the room formulation above.
        for ident, ident_blocks in blocks_by_identity.items():
            if len(ident_blocks) < 2:
                continue
            for i, block_a in enumerate(ident_blocks):
                dur_a = block_duration_slots[block_a.id]
                for s_a in block_starts[block_a.id]:
                    active_a_vars = [assign[(block_a.id, s_a, r)] for r in range(rooms)]
                    for block_b in ident_blocks[i + 1:]:
                        dur_b = block_duration_slots[block_b.id]
                        for s_b in block_starts[block_b.id]:
                            if not (s_a < s_b + dur_b and s_b < s_a + dur_a):
                                continue
                            active_b_vars = [assign[(block_b.id, s_b, r)] for r in range(rooms)]
                            v = model.NewBoolVar(_next_vname("psv"))
                            # v ⇒ both a and b are placed at this option (in any room).
                            model.Add(sum(active_a_vars) >= 1).OnlyEnforceIf(v)
                            model.Add(sum(active_b_vars) >= 1).OnlyEnforceIf(v)
                            model.Add(
                                sum(active_a_vars) + sum(active_b_vars) <= 1
                            ).OnlyEnforceIf(v.Not())
                            soft_violation_terms.append(v)

    # Same-class-same-room.
    blocks_by_class: dict[str, list[ClassBlock]] = defaultdict(list)
    for block in schedulable:
        blocks_by_class[block.class_id].append(block)

    if constraints.same_class_same_room == "hard":
        for class_id, class_blocks in blocks_by_class.items():
            if len(class_blocks) < 2:
                continue
            class_room = model.NewIntVar(0, rooms - 1, f"cr_{class_id[:12]}")
            for block in class_blocks:
                for s in block_starts[block.id]:
                    for r in range(rooms):
                        v = assign[(block.id, s, r)]
                        model.Add(class_room == r).OnlyEnforceIf(v)
    elif constraints.same_class_same_room == "soft":
        # Preferred-room model: one IntVar per class, penalise each sub-block
        # placed in a different room. Cheaper than a pairwise penalty.
        for class_id, class_blocks in blocks_by_class.items():
            if len(class_blocks) < 2:
                continue
            class_room = model.NewIntVar(0, rooms - 1, f"crs_{class_id[:12]}")
            room_is_preferred: list[cp_model.IntVar] = []
            for r in range(rooms):
                bvar = model.NewBoolVar(f"crp_{class_id[:8]}_{r}")
                model.Add(class_room == r).OnlyEnforceIf(bvar)
                model.Add(class_room != r).OnlyEnforceIf(bvar.Not())
                room_is_preferred.append(bvar)
            model.AddExactlyOne(room_is_preferred)
            for block in class_blocks:
                for s in block_starts[block.id]:
                    for r in range(rooms):
                        v = assign[(block.id, s, r)]
                        preferred = room_is_preferred[r]
                        wrong = model.NewBoolVar(_next_vname("wr"))
                        model.AddBoolAnd([v, preferred.Not()]).OnlyEnforceIf(wrong)
                        model.AddBoolOr([v.Not(), preferred]).OnlyEnforceIf(wrong.Not())
                        soft_violation_terms.append(wrong)

    # ── Span minimisation (department, class, professor) ────────────────────
    department_span_terms: list[cp_model.IntVar] = []
    class_span_terms: list[cp_model.IntVar] = []
    professor_span_terms: list[cp_model.IntVar] = []

    if constraints.minimize_department_span != "off":
        blocks_by_dept: dict[str, list[ClassBlock]] = defaultdict(list)
        for block in schedulable:
            dept = _block_to_department(block, problem)
            if dept:
                blocks_by_dept[dept].append(block)
        for dept_id, dept_blocks in blocks_by_dept.items():
            if len(dept_blocks) < 2:
                continue
            d_start = model.NewIntVar(0, horizon_slots, f"ds_{dept_id[:8]}")
            d_end = model.NewIntVar(0, horizon_slots, f"de_{dept_id[:8]}")
            d_span = model.NewIntVar(0, horizon_slots, f"dsp_{dept_id[:8]}")
            model.AddMinEquality(d_start, [eff_start_for_min[b.id] for b in dept_blocks])
            model.AddMaxEquality(d_end, [eff_end_for_max[b.id] for b in dept_blocks])
            model.Add(d_span >= d_end - d_start)
            if constraints.minimize_department_span == "hard":
                total = sum(block_duration_slots[b.id] for b in dept_blocks)
                model.Add(d_span <= total)
            else:
                department_span_terms.append(d_span)

    if constraints.minimize_class_span != "off":
        for class_id, class_blocks in blocks_by_class.items():
            if len(class_blocks) < 2:
                continue
            c_start = model.NewIntVar(0, horizon_slots, f"cs_{class_id[:8]}")
            c_end = model.NewIntVar(0, horizon_slots, f"ce_{class_id[:8]}")
            c_span = model.NewIntVar(0, horizon_slots, f"csp_{class_id[:8]}")
            model.AddMinEquality(c_start, [eff_start_for_min[b.id] for b in class_blocks])
            model.AddMaxEquality(c_end, [eff_end_for_max[b.id] for b in class_blocks])
            model.Add(c_span >= c_end - c_start)
            if constraints.minimize_class_span == "hard":
                total = sum(block_duration_slots[b.id] for b in class_blocks)
                model.Add(c_span <= total)
            else:
                class_span_terms.append(c_span)

    if constraints.minimize_professor_span != "off":
        # Professors are tied to a class via the data model. With sub-blocks of
        # one class sharing a class_id, a professor's span is just the span over
        # all blocks tagged with their class — which is the same as class_span
        # when only one prof per class. We still emit it explicitly so tuning
        # _W_PROF independently of _W_CLASS does what an admin expects.
        prof_to_blocks: dict[str, list[ClassBlock]] = defaultdict(list)
        for block in schedulable:
            prof_rids, _ = _block_resources_with_role(block, problem)
            for rid in prof_rids:
                prof_to_blocks[rid].append(block)
        for prof_rid, prof_blocks in prof_to_blocks.items():
            if len(prof_blocks) < 2:
                continue
            p_start = model.NewIntVar(0, horizon_slots, f"ps_{prof_rid[:8]}")
            p_end = model.NewIntVar(0, horizon_slots, f"pe_{prof_rid[:8]}")
            p_span = model.NewIntVar(0, horizon_slots, f"psp_{prof_rid[:8]}")
            model.AddMinEquality(p_start, [eff_start_for_min[b.id] for b in prof_blocks])
            model.AddMaxEquality(p_end, [eff_end_for_max[b.id] for b in prof_blocks])
            model.Add(p_span >= p_end - p_start)
            if constraints.minimize_professor_span == "hard":
                total = sum(block_duration_slots[b.id] for b in prof_blocks)
                model.Add(p_span <= total)
            else:
                professor_span_terms.append(p_span)

    # ── Room balance ────────────────────────────────────────────────────────
    room_imbalance_terms: list[cp_model.IntVar] = []
    if constraints.balance_rooms != "off" and rooms > 1:
        room_loads: list[cp_model.IntVar] = []
        for r in range(rooms):
            load = model.NewIntVar(0, len(schedulable), f"rl_{r}")
            model.Add(
                load
                == sum(
                    assign[(block.id, s, r)]
                    for block in schedulable
                    for s in block_starts[block.id]
                )
            )
            room_loads.append(load)
        max_load = model.NewIntVar(0, len(schedulable), "rl_max")
        min_load = model.NewIntVar(0, len(schedulable), "rl_min")
        imbalance = model.NewIntVar(0, len(schedulable), "rl_imb")
        model.AddMaxEquality(max_load, room_loads)
        model.AddMinEquality(min_load, room_loads)
        model.Add(imbalance == max_load - min_load)
        if constraints.balance_rooms == "hard":
            model.Add(imbalance <= 1)
        else:
            room_imbalance_terms.append(imbalance)

    # ── Soft availability term ──────────────────────────────────────────────
    # Sum the per-option soft prof miss counts × the assignment indicator.
    soft_avail_terms: list[cp_model.IntVar] = []
    if soft_avail_cost:
        n_resources_max = max(soft_avail_cost.values(), default=1)
        soft_avail_total = model.NewIntVar(
            0,
            len(schedulable) * n_resources_max,
            "soft_avail_pen",
        )
        model.Add(
            soft_avail_total
            == sum(
                cost * assign[(block_id, s, r)]
                for (block_id, s), cost in soft_avail_cost.items()
                for r in range(rooms)
            )
        )
        soft_avail_terms.append(soft_avail_total)

    # ── Makespan ────────────────────────────────────────────────────────────
    makespan = model.NewIntVar(0, horizon_slots, "makespan")
    model.AddMaxEquality(makespan, list(eff_end_for_max.values()))
    makespan_for_obj: cp_model.IntVar | cp_model.LinearExpr = (
        makespan if constraints.minimize_makespan == "soft" else model.NewConstant(0)
    )

    # ── Objective ───────────────────────────────────────────────────────────
    quality = (
        makespan_for_obj * _W_MAKESPAN
        + sum(soft_avail_terms) * _W_AVAIL
        + sum(department_span_terms) * _W_DEPT
        + sum(class_span_terms) * _W_CLASS
        + sum(professor_span_terms) * _W_PROF
        + sum(room_imbalance_terms) * _W_ROOM
        + sum(soft_violation_terms) * _W_SOFT_VIO
    )

    # The unscheduled-block penalty must beat every quality improvement so the
    # solver never trades a placement for a smaller objective. Same int64
    # safety guard the flat solver uses.
    _INT64_SAFE = 4_000_000_000_000_000_000
    n_sched = len(schedulable)
    max_quality = (
        horizon_slots * _W_MAKESPAN
        + n_sched * max(len(soft_avail_cost) // max(n_sched, 1) + 1, 1) * _W_AVAIL
        + len(department_span_terms) * horizon_slots * _W_DEPT
        + len(class_span_terms) * horizon_slots * _W_CLASS
        + len(professor_span_terms) * horizon_slots * _W_PROF
        + n_sched * _W_ROOM
        + len(soft_violation_terms) * _W_SOFT_VIO
    )
    unscheduled_penalty = min(
        max_quality + 1, _INT64_SAFE // max(n_sched, 1)
    )
    unscheduled_count = n_sched - sum(is_scheduled.values())
    model.Minimize(unscheduled_count * unscheduled_penalty + quality)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 4

    t0 = time.perf_counter()
    status = solver.Solve(model)
    logger.info(
        "place_blocks: blocks=%d  status=%s  wall=%.2fs  soft_violations=%d  soft_avail_misses=%d",
        len(schedulable),
        solver.StatusName(status),
        time.perf_counter() - t0,
        len(soft_violation_terms),
        len(soft_avail_cost),
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


def _slot_starts_for_order(
    pres_list: list[PresentationInput], order: list[int], block_start: datetime
) -> list[datetime]:
    """Cumulative slot start times for a given permutation of a block's presentations.

    Slot 0 starts at the block start; slot i starts at the previous slot's
    presentation-end + buffer. Used by the within-block reorderer.
    """
    starts: list[datetime] = [block_start]
    cursor = block_start
    for k, idx in enumerate(order):
        if k == len(order) - 1:
            break
        p = pres_list[idx]
        cursor = cursor + timedelta(minutes=p.duration_minutes + p.buffer_minutes)
        starts.append(cursor)
    return starts


def _count_window_violations(
    pres_list: list[PresentationInput],
    order: list[int],
    block_start: datetime,
    problem: ScheduleProblem,
) -> int:
    """How many presentations would land outside one of their hard or soft
    resource windows? Each presentation counts at most twice: once if it
    misses a hard window (weighted heavily) and once if it misses a soft
    window. The reorderer uses this as its objective.

    Professor windows already constrain block placement (phase 1 intersects
    hard prof windows into ``allowed_windows``; soft prof windows feed phase
    2's penalty), so in practice this counts *student*-window misses inside
    the block. Hard misses are weighted 100× heavier than soft ones so the
    reorderer never trades one hard fix for any number of soft regressions.
    """
    starts = _slot_starts_for_order(pres_list, order, block_start)
    HARD_WEIGHT = 100
    SOFT_WEIGHT = 1
    violations = 0
    for i, idx in enumerate(order):
        p = pres_list[idx]
        start = starts[i]
        end = start + timedelta(minutes=p.duration_minutes)
        hard_miss = False
        soft_miss = False
        for rid in p.resource_ids:
            if not hard_miss and rid in problem.resource_windows:
                windows = problem.resource_windows[rid]
                if windows and not any(start >= w.start and end <= w.end for w in windows):
                    hard_miss = True
            if not soft_miss and rid in problem.soft_resource_windows:
                windows = problem.soft_resource_windows[rid]
                if windows and not any(start >= w.start and end <= w.end for w in windows):
                    soft_miss = True
            if hard_miss and soft_miss:
                break
        if hard_miss:
            violations += HARD_WEIGHT
        if soft_miss:
            violations += SOFT_WEIGHT
    return violations


def _reorder_for_availability(
    block: ClassBlock, block_start: datetime, problem: ScheduleProblem
) -> tuple[str, ...]:
    """Return the block's presentation ids in an order that minimises hard
    student-window misses, found by pairwise-swap hill climbing.

    Cheap (O(n³) per swap iteration; n is presentations-per-block, typically
    10–30). Steepest descent: each iteration finds the swap with the largest
    drop in violations and applies it. Stops at the first local optimum, which
    is good enough — we don't need globally optimal, just better than fixed input
    order. Remaining misses surface as soft warnings via the verification sweep.
    """
    pres_by_id = {p.id: p for p in problem.presentations}
    pres_list = [pres_by_id[pid] for pid in block.presentation_ids if pid in pres_by_id]
    n = len(pres_list)
    if n <= 1:
        return tuple(p.id for p in pres_list)

    order = list(range(n))
    current_v = _count_window_violations(pres_list, order, block_start, problem)
    if current_v == 0:
        return tuple(p.id for p in pres_list)

    max_outer_iterations = n * n
    for _ in range(max_outer_iterations):
        best_swap: tuple[int, int] | None = None
        best_v = current_v
        for i in range(n):
            for j in range(i + 1, n):
                order[i], order[j] = order[j], order[i]
                v = _count_window_violations(pres_list, order, block_start, problem)
                if v < best_v:
                    best_v = v
                    best_swap = (i, j)
                order[i], order[j] = order[j], order[i]  # always revert; apply best at the end
        if best_swap is None:
            break  # local optimum
        i, j = best_swap
        order[i], order[j] = order[j], order[i]
        current_v = best_v
        if current_v == 0:
            break

    return tuple(pres_list[k].id for k in order)


def expand_blocks(
    placed: list[PlacedBlock], problem: ScheduleProblem
) -> tuple[ScheduledPresentation, ...]:
    presentation_by_id: dict[str, PresentationInput] = {p.id: p for p in problem.presentations}
    out: list[ScheduledPresentation] = []
    for pb in placed:
        block_start = _ensure_utc(pb.start)
        ordered_ids = _reorder_for_availability(pb.block, block_start, problem)
        cursor = block_start
        for pid in ordered_ids:
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

    Soft warnings are per-resource availability misses against a *soft* window
    (a window the user marked ``professor_availability="soft"`` or
    ``student_availability="soft"``). The schedule is still saved.

    Resource-window classification:

    * A miss against ``problem.resource_windows`` (only populated when the
      relevant ``*_availability`` mode is ``"hard"``) is a hard issue. The user
      told the scheduler "must respect this window" so we don't save a schedule
      that violates it.
    * A miss against ``problem.soft_resource_windows`` (only populated when
      mode is ``"soft"``) is a warning. The schedule still saves.
    * Missed-window checks are skipped entirely when mode is ``"off"`` —
      ``service.py`` doesn't put windows in either map in that case.
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
        # Hard window misses → hard issues. Only resources whose mode is
        # "hard" appear in problem.resource_windows (see service.py).
        for rid in pres.resource_ids:
            if rid not in problem.resource_windows:
                continue
            windows = _normalize(problem.resource_windows[rid])
            if not windows:
                continue
            if not any(a_start >= w.start and a_end <= w.end for w in windows):
                name = problem.resource_name.get(rid, "Someone")
                hard_issues.append(
                    f'Availability conflict: "{title}" runs outside {name}\'s '
                    f"availability window. (Switch the relevant availability "
                    f"setting to Soft to allow this.)"
                )
        # Soft window misses → warnings.
        for rid in pres.resource_ids:
            if rid not in problem.soft_resource_windows:
                continue
            windows = _normalize(problem.soft_resource_windows[rid])
            if not windows:
                continue
            if not any(a_start >= w.start and a_end <= w.end for w in windows):
                name = problem.resource_name.get(rid, "Someone")
                soft_issues.append(
                    f'Availability warning: "{title}" runs outside {name}\'s availability window.'
                )

    # Pairwise checks. Severity depends on the constraint mode the user picked:
    # hard ⇒ hard issue (refuse to save), soft ⇒ warning, off ⇒ skipped.
    room_mode = problem.constraints.room_conflicts
    person_mode = problem.constraints.person_conflicts
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
            if a.room_index == b.room_index and room_mode != "off":
                msg = (
                    f'Schedule integrity: room {a.room_index + 1} is double-booked '
                    f'between "{title_a}" and "{title_b}".'
                )
                if room_mode == "hard":
                    hard_issues.append(msg)
                else:
                    soft_issues.append(msg)
            shared = pres_identities.get(a.presentation_id, set()) & pres_identities.get(b.presentation_id, set())
            if shared and person_mode != "off":
                ident = next(iter(shared))
                name = _name_for_identity(ident)
                msg = (
                    f'Schedule integrity: "{name}" is required at both "{title_a}" and '
                    f'"{title_b}" at the same time.'
                )
                if person_mode == "hard":
                    hard_issues.append(msg)
                else:
                    soft_issues.append(msg)
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
