"""Hard-constraint correctness checks for scheduler results.

Every scheduler result — even one the solver labeled `optimal`/`feasible` —
gets put through every check here. A failure on a "successful" result is a
**critical** correctness bug.

Each check returns a `CheckResult(passed, reason, offending)`. The runner
aggregates all checks per scenario into a `VerificationReport`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from app.scheduler.models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduleProblem,
    ScheduleResult,
    ScheduledPresentation,
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    reason: str = ""
    offending: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "offending": list(self.offending),
        }


@dataclass(frozen=True)
class VerificationReport:
    checks: tuple[CheckResult, ...]

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "all_passed": self.all_passed,
            "checks": [c.to_dict() for c in self.checks],
        }


# ── Helpers ───────────────────────────────────────────────────────────────


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _within_any_window(
    start: datetime, end: datetime, windows: Iterable[AvailabilityWindow]
) -> bool:
    return any(start >= w.start and end <= w.end for w in windows)


def _presentations_by_id(problem: ScheduleProblem) -> dict[str, PresentationInput]:
    return {p.id: p for p in problem.presentations}


# ── Individual checks ─────────────────────────────────────────────────────


def check_no_room_overlap(result: ScheduleResult) -> CheckResult:
    by_room: dict[int, list[ScheduledPresentation]] = defaultdict(list)
    for a in result.assignments:
        by_room[a.room_index].append(a)
    for room, items in by_room.items():
        items.sort(key=lambda x: x.start)
        for i in range(len(items) - 1):
            if items[i].end > items[i + 1].start:
                return CheckResult(
                    name="no_room_overlap",
                    passed=False,
                    reason=(
                        f"Room {room}: '{items[i].presentation_id}' "
                        f"({items[i].start}–{items[i].end}) overlaps "
                        f"'{items[i + 1].presentation_id}' "
                        f"({items[i + 1].start}–{items[i + 1].end})"
                    ),
                    offending=(items[i].presentation_id, items[i + 1].presentation_id),
                )
    return CheckResult(name="no_room_overlap", passed=True)


def check_no_resource_overlap(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    pres_by_id = _presentations_by_id(problem)
    identity = problem.resource_identity or {}
    by_canonical: dict[str, list[ScheduledPresentation]] = defaultdict(list)
    for a in result.assignments:
        pres = pres_by_id.get(a.presentation_id)
        if pres is None:
            continue
        for rid in pres.resource_ids:
            canonical = identity.get(rid, rid)
            by_canonical[canonical].append(a)

    for canonical, items in by_canonical.items():
        items.sort(key=lambda x: x.start)
        for i in range(len(items) - 1):
            if _overlaps(items[i].start, items[i].end, items[i + 1].start, items[i + 1].end):
                return CheckResult(
                    name="no_resource_overlap",
                    passed=False,
                    reason=(
                        f"Resource '{canonical}' double-booked: "
                        f"'{items[i].presentation_id}' "
                        f"({items[i].start}–{items[i].end}) overlaps "
                        f"'{items[i + 1].presentation_id}' "
                        f"({items[i + 1].start}–{items[i + 1].end})"
                    ),
                    offending=(items[i].presentation_id, items[i + 1].presentation_id),
                )
    return CheckResult(name="no_resource_overlap", passed=True)


def check_all_in_symposium_window(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    if problem.constraints.symposium_windows != "hard":
        return CheckResult(name="all_in_symposium_window", passed=True, reason="not enforced")
    bad = [
        a.presentation_id
        for a in result.assignments
        if not _within_any_window(a.start, a.end, problem.symposium_windows)
    ]
    if bad:
        return CheckResult(
            name="all_in_symposium_window",
            passed=False,
            reason=f"{len(bad)} assignments outside any symposium window",
            offending=tuple(bad),
        )
    return CheckResult(name="all_in_symposium_window", passed=True)


def check_all_in_prof_window(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    if problem.constraints.professor_availability != "hard":
        return CheckResult(name="all_in_prof_window", passed=True, reason="not enforced")
    pres_by_id = _presentations_by_id(problem)
    prof_ids = set(problem.professor_resource_ids)
    bad: list[str] = []
    for a in result.assignments:
        pres = pres_by_id.get(a.presentation_id)
        if pres is None:
            continue
        for rid in pres.resource_ids:
            if rid in prof_ids:
                windows = problem.resource_windows.get(rid, ())
                if windows and not _within_any_window(a.start, a.end, windows):
                    bad.append(a.presentation_id)
                    break
    if bad:
        return CheckResult(
            name="all_in_prof_window",
            passed=False,
            reason=f"{len(bad)} assignments outside required prof window",
            offending=tuple(bad),
        )
    return CheckResult(name="all_in_prof_window", passed=True)


def check_same_class_same_room(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    if problem.constraints.same_class_same_room != "hard":
        return CheckResult(name="same_class_same_room", passed=True, reason="not enforced")
    pres_by_id = _presentations_by_id(problem)
    class_to_room: dict[str, int] = {}
    for a in result.assignments:
        pres = pres_by_id.get(a.presentation_id)
        if pres is None or not pres.class_id:
            continue
        if pres.class_id in class_to_room:
            if class_to_room[pres.class_id] != a.room_index:
                return CheckResult(
                    name="same_class_same_room",
                    passed=False,
                    reason=(
                        f"Class '{pres.class_id}' split across rooms "
                        f"{class_to_room[pres.class_id]} and {a.room_index}"
                    ),
                    offending=(pres.class_id,),
                )
        else:
            class_to_room[pres.class_id] = a.room_index
    return CheckResult(name="same_class_same_room", passed=True)


def check_buffer_respected(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    """Within a room, gap between adjacent assignments ≥ buffer of the earlier."""
    pres_by_id = _presentations_by_id(problem)
    by_room: dict[int, list[ScheduledPresentation]] = defaultdict(list)
    for a in result.assignments:
        by_room[a.room_index].append(a)
    for room, items in by_room.items():
        items.sort(key=lambda x: x.start)
        for i in range(len(items) - 1):
            earlier = items[i]
            later = items[i + 1]
            buf = pres_by_id[earlier.presentation_id].buffer_minutes
            gap_minutes = (later.start - earlier.end).total_seconds() / 60.0
            if gap_minutes + 1e-6 < buf:
                return CheckResult(
                    name="buffer_respected",
                    passed=False,
                    reason=(
                        f"Room {room}: gap of {gap_minutes:.1f} min after "
                        f"'{earlier.presentation_id}' is below required "
                        f"buffer {buf} min before '{later.presentation_id}'"
                    ),
                    offending=(earlier.presentation_id, later.presentation_id),
                )
    return CheckResult(name="buffer_respected", passed=True)


def check_slot_aligned(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    if not result.assignments or not problem.symposium_windows:
        return CheckResult(name="slot_aligned", passed=True)
    base = min(w.start for w in problem.symposium_windows)
    slot = problem.slot_minutes
    bad = []
    for a in result.assignments:
        offset_seconds = (a.start - base).total_seconds()
        if abs((offset_seconds / 60.0) % slot) > 1e-6 and abs(((offset_seconds / 60.0) % slot) - slot) > 1e-6:
            bad.append(a.presentation_id)
    if bad:
        return CheckResult(
            name="slot_aligned",
            passed=False,
            reason=f"{len(bad)} assignments not aligned to {slot}-min slots",
            offending=tuple(bad),
        )
    return CheckResult(name="slot_aligned", passed=True)


def check_room_index_in_range(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    bad = [
        a.presentation_id
        for a in result.assignments
        if not (0 <= a.room_index < problem.rooms_available)
    ]
    if bad:
        return CheckResult(
            name="room_index_in_range",
            passed=False,
            reason=f"{len(bad)} assignments use invalid room_index",
            offending=tuple(bad),
        )
    return CheckResult(name="room_index_in_range", passed=True)


def check_assignments_unique(result: ScheduleResult) -> CheckResult:
    seen: dict[str, int] = defaultdict(int)
    for a in result.assignments:
        seen[a.presentation_id] += 1
    dups = [pid for pid, n in seen.items() if n > 1]
    if dups:
        return CheckResult(
            name="assignments_unique",
            passed=False,
            reason=f"{len(dups)} presentations scheduled more than once",
            offending=tuple(dups),
        )
    return CheckResult(name="assignments_unique", passed=True)


def check_unscheduled_consistent(
    problem: ScheduleProblem, result: ScheduleResult
) -> CheckResult:
    # When the solver bails with "invalid" it doesn't populate
    # unscheduled_presentations; that's not a correctness violation per se.
    if result.status == "invalid":
        return CheckResult(
            name="unscheduled_consistent",
            passed=True,
            reason="solver returned 'invalid'; unscheduled list not populated by design",
        )
    all_ids = {p.id for p in problem.presentations}
    scheduled = {a.presentation_id for a in result.assignments}
    unscheduled = set(result.unscheduled_presentations)
    union = scheduled | unscheduled
    intersection = scheduled & unscheduled
    extras = scheduled - all_ids
    missing = all_ids - union

    issues = []
    if extras:
        issues.append(f"{len(extras)} scheduled IDs not in input")
    if missing:
        issues.append(f"{len(missing)} input IDs neither scheduled nor unscheduled")
    if intersection:
        issues.append(f"{len(intersection)} IDs in both scheduled and unscheduled")

    if issues:
        return CheckResult(
            name="unscheduled_consistent",
            passed=False,
            reason="; ".join(issues),
            offending=tuple(extras | missing | intersection),
        )
    return CheckResult(name="unscheduled_consistent", passed=True)


# ── Aggregator ────────────────────────────────────────────────────────────


def verify(problem: ScheduleProblem, result: ScheduleResult) -> VerificationReport:
    """Run every check and bundle the results."""
    return VerificationReport(
        checks=(
            check_no_room_overlap(result),
            check_no_resource_overlap(problem, result),
            check_all_in_symposium_window(problem, result),
            check_all_in_prof_window(problem, result),
            check_same_class_same_room(problem, result),
            check_buffer_respected(problem, result),
            check_slot_aligned(problem, result),
            check_room_index_in_range(problem, result),
            check_assignments_unique(result),
            check_unscheduled_consistent(problem, result),
        )
    )
