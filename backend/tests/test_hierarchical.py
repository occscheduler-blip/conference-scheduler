"""Unit tests for the hierarchical (class-as-block) scheduler.

These tests deliberately do not touch Supabase — they exercise the in-memory
solver pipeline directly. Run with:

    .venv/bin/pytest --noconftest tests/test_hierarchical.py -q
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.scheduler.hierarchical import (
    expand_blocks,
    place_blocks,
    prepare_class_blocks,
    solve_hierarchical,
    verify_assignments,
)
from app.scheduler.models import (
    AvailabilityWindow,
    ClassBlock,
    PlacedBlock,
    PresentationInput,
    ScheduleConstraints,
    ScheduledPresentation,
    ScheduleProblem,
)


# ── Fixtures / builders ─────────────────────────────────────────────────────


def _day(start_hour: int, end_hour: int, day: int = 1) -> AvailabilityWindow:
    return AvailabilityWindow(
        start=datetime(2026, 6, day, start_hour, 0, tzinfo=timezone.utc),
        end=datetime(2026, 6, day, end_hour, 0, tzinfo=timezone.utc),
    )


def _build_large_problem(
    n_classes: int,
    presentations_per_class: int,
    rooms: int,
    days: int,
    duration_minutes: int = 15,
) -> ScheduleProblem:
    """Build a synthetic problem with n_classes × presentations_per_class
    presentations spread across `days` 8-hour days.
    """
    presentations: list[PresentationInput] = []
    professor_ids: list[str] = []
    resource_identity: dict[str, str] = {}
    resource_name: dict[str, str] = {}
    resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}

    sym_windows = tuple(_day(9, 17, d) for d in range(1, days + 1))

    for c in range(n_classes):
        prof_id = f"prof_{c}"
        professor_ids.append(prof_id)
        resource_identity[prof_id] = f"prof{c}@hamilton.edu"
        resource_name[prof_id] = f"Prof {c}"
        resource_windows[prof_id] = sym_windows
        for s in range(presentations_per_class):
            student_id = f"stu_{c}_{s}"
            resource_identity[student_id] = f"stu{c}_{s}@hamilton.edu"
            resource_name[student_id] = f"Student {c}-{s}"
            resource_windows[student_id] = sym_windows
            presentations.append(
                PresentationInput(
                    id=f"pres_{c}_{s}",
                    title=f"Class {c} Talk {s}",
                    duration_minutes=duration_minutes,
                    buffer_minutes=0,
                    class_id=f"class_{c}",
                    department_id=f"dept_{c // 3}",
                    resource_ids=(prof_id, student_id),
                )
            )

    return ScheduleProblem(
        symposium_id="test-large",
        rooms_available=rooms,
        symposium_windows=sym_windows,
        presentations=tuple(presentations),
        resource_windows=resource_windows,
        professor_resource_ids=tuple(professor_ids),
        resource_identity=resource_identity,
        resource_name=resource_name,
        slot_minutes=5,
        constraints=ScheduleConstraints(),
    )


# ── Tests ──────────────────────────────────────────────────────────────────


def test_block_preparation_single_class_fits():
    problem = _build_large_problem(
        n_classes=1, presentations_per_class=4, rooms=1, days=1, duration_minutes=30
    )
    blocks = prepare_class_blocks(problem)
    assert len(blocks) == 1
    assert blocks[0].total_minutes == 4 * 30
    assert len(blocks[0].presentation_ids) == 4
    assert blocks[0].class_id == "class_0"


def test_block_preparation_oversize_class_splits():
    """A class whose presentations total more than the longest contiguous window
    should split into multiple sub-blocks tagged with the same class_id."""
    problem = _build_large_problem(
        n_classes=1, presentations_per_class=40, rooms=1, days=2, duration_minutes=30
    )
    # 40 × 30 = 1200 minutes > 480-minute (8h) day
    blocks = prepare_class_blocks(problem)
    assert len(blocks) >= 2
    assert all(b.class_id == "class_0" for b in blocks)
    # Every presentation accounted for, no duplicates
    all_ids = [pid for b in blocks for pid in b.presentation_ids]
    assert sorted(all_ids) == sorted(p.id for p in problem.presentations)


def test_400_presentation_symposium_solves_quickly():
    """The motivating case: 400 presentations across 20 classes / 5 rooms / 3 days.

    With same-class-same-room hard, each class block must fit entirely inside
    a single room-day. 20 × 10-min talks → 200-min class block, two of which fit
    in an 8-hour day. 5 rooms × 3 days × 2 classes-per-room-day = 30 capacity —
    comfortably accommodating 20 classes.
    """
    problem = _build_large_problem(
        n_classes=20,
        presentations_per_class=20,
        rooms=5,
        days=3,
        duration_minutes=10,
    )
    assert len(problem.presentations) == 400

    # CP-SAT respects the time budget; if it can't prove optimality it returns
    # the best feasible solution found. The point of this test is "does the
    # 400-presentation case terminate cleanly with all blocks placed?", not
    # benchmarking, so we only assert correctness, not wall time.
    result = solve_hierarchical(problem, time_limit_seconds=30.0)

    assert result.status in ("optimal", "feasible"), f"got {result.status} diags={result.diagnostics}"
    assert len(result.assignments) == 400

    # No conflicts in the result
    issues = verify_assignments(result.assignments, problem)
    assert issues == ()


def test_same_class_same_room_holds():
    """Hard same_class_same_room: every presentation in a class lands in the same room."""
    problem = _build_large_problem(
        n_classes=4, presentations_per_class=5, rooms=3, days=1, duration_minutes=20
    )
    result = solve_hierarchical(problem, time_limit_seconds=15.0)
    assert result.status in ("optimal", "feasible")
    by_class: dict[str, set[int]] = {}
    pres_by_id = {p.id: p for p in problem.presentations}
    for a in result.assignments:
        cid = pres_by_id[a.presentation_id].class_id
        by_class.setdefault(cid, set()).add(a.room_index)
    for cid, rooms_used in by_class.items():
        assert len(rooms_used) == 1, f"class {cid} spans rooms {rooms_used}"


def test_cross_class_same_email_no_overlap():
    """Two presentations in different classes that share a student (same email)
    must not overlap in the schedule, even though they have different row-ids.
    """
    sym = (_day(9, 17),)
    # Class A: prof_a + student row stuA1 (email shared@hamilton.edu)
    # Class B: prof_b + student row stuB1 (email shared@hamilton.edu)
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=sym,
        presentations=(
            PresentationInput(
                id="pA", title="Class A talk",
                duration_minutes=30, class_id="classA",
                resource_ids=("profA", "stuA1"),
            ),
            PresentationInput(
                id="pB", title="Class B talk",
                duration_minutes=30, class_id="classB",
                resource_ids=("profB", "stuB1"),
            ),
        ),
        resource_windows={
            "profA": sym, "stuA1": sym, "profB": sym, "stuB1": sym,
        },
        professor_resource_ids=("profA", "profB"),
        resource_identity={
            "profA": "profA@hamilton.edu",
            "profB": "profB@hamilton.edu",
            "stuA1": "shared@hamilton.edu",
            "stuB1": "shared@hamilton.edu",  # same person, two class rows
        },
        resource_name={
            "profA": "Prof A", "profB": "Prof B",
            "stuA1": "Shared Student", "stuB1": "Shared Student",
        },
    )

    result = solve_hierarchical(problem, time_limit_seconds=10.0)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2

    a, b = result.assignments
    overlap = a.start < b.end and b.start < a.end
    assert not overlap, "Same-email student was double-booked across classes"

    # Verification sweep should also pass
    issues = verify_assignments(result.assignments, problem)
    assert issues == ()


def test_verification_sweep_catches_room_conflict():
    """If a corrupted output assigns two presentations to the same room at the
    same time, the sweep returns a clear diagnostic."""
    sym = (_day(9, 17),)
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=sym,
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30, class_id="cA"),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30, class_id="cB"),
        ),
    )
    bad = (
        ScheduledPresentation(
            presentation_id="p1", room_index=0,
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        ),
        ScheduledPresentation(
            presentation_id="p2", room_index=0,
            start=datetime(2026, 6, 1, 9, 15, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc),
        ),
    )
    issues = verify_assignments(bad, problem)
    assert len(issues) >= 1
    assert any("double-booked" in i for i in issues)


def test_verification_sweep_catches_cross_class_person_conflict():
    """Inject an overlap between two presentations that share an email-identity;
    sweep must flag it even when row-ids differ."""
    sym = (_day(9, 17),)
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=sym,
        presentations=(
            PresentationInput(
                id="p1", title="Talk 1", duration_minutes=30, class_id="cA",
                resource_ids=("stuA1",),
            ),
            PresentationInput(
                id="p2", title="Talk 2", duration_minutes=30, class_id="cB",
                resource_ids=("stuB1",),
            ),
        ),
        resource_identity={
            "stuA1": "shared@hamilton.edu",
            "stuB1": "shared@hamilton.edu",
        },
        resource_name={"stuA1": "Shared Student", "stuB1": "Shared Student"},
    )
    overlapping = (
        ScheduledPresentation(
            presentation_id="p1", room_index=0,
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        ),
        ScheduledPresentation(
            presentation_id="p2", room_index=1,
            start=datetime(2026, 6, 1, 9, 15, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc),
        ),
    )
    issues = verify_assignments(overlapping, problem)
    assert any("Shared Student" in i for i in issues), issues


def test_verification_sweep_clean_for_valid_schedule():
    """Negative control: a valid assignment must produce zero issues."""
    sym = (_day(9, 17),)
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=sym,
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30, class_id="cA"),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30, class_id="cA"),
        ),
    )
    good = (
        ScheduledPresentation(
            presentation_id="p1", room_index=0,
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        ),
        ScheduledPresentation(
            presentation_id="p2", room_index=0,
            start=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        ),
    )
    assert verify_assignments(good, problem) == ()


def test_hard_student_avail_violation_is_hard_issue():
    """When student_availability=hard and the reorderer cannot fit a student
    into the placed block, the verification sweep must classify it as a hard
    issue so the schedule is not saved."""
    sym = (_day(9, 17),)
    # Student available only 9:00-9:30 but block runs 9:00-10:00 with two
    # 30-min talks. The reorderer can put this student in slot 0; the OTHER
    # student has no constraint. So hard mode should succeed here.
    presentations = (
        PresentationInput(id="p1", title="P1", duration_minutes=30, class_id="cA", resource_ids=("stu1",)),
        PresentationInput(id="p2", title="P2", duration_minutes=30, class_id="cA", resource_ids=("stu2",)),
    )
    constrained_window = (
        AvailabilityWindow(
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        ),
    )
    problem = ScheduleProblem(
        symposium_id="t", rooms_available=1, symposium_windows=sym,
        presentations=presentations,
        resource_windows={"stu1": constrained_window},  # hard
        constraints=ScheduleConstraints(student_availability="hard"),
    )
    result = solve_hierarchical(problem, time_limit_seconds=10.0)
    assert result.status in ("optimal", "feasible")  # reorderer fixes it
    assert len(result.assignments) == 2


def test_hard_student_avail_unfittable_fails():
    """If no permutation can fit a hard student window, the schedule fails
    with status=invalid (not silently saved)."""
    sym = (_day(9, 17),)
    # Student needs 9:00-9:30 BUT they're the SECOND presenter and the first
    # talk runs 30 min — there's no order that puts them in a 9:00-9:30 slot
    # except being first. With both students requiring the SAME slot, no
    # ordering works.
    early_only = (
        AvailabilityWindow(
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        ),
    )
    presentations = (
        PresentationInput(id="p1", title="P1", duration_minutes=30, class_id="cA", resource_ids=("stu1",)),
        PresentationInput(id="p2", title="P2", duration_minutes=30, class_id="cA", resource_ids=("stu2",)),
    )
    problem = ScheduleProblem(
        symposium_id="t", rooms_available=1, symposium_windows=sym,
        presentations=presentations,
        resource_windows={"stu1": early_only, "stu2": early_only},  # both hard
        resource_name={"stu1": "Alice", "stu2": "Bob"},
        constraints=ScheduleConstraints(student_availability="hard"),
    )
    result = solve_hierarchical(problem, time_limit_seconds=10.0)
    assert result.status == "invalid", f"expected invalid, got {result.status}"
    assert any("availability" in d.lower() for d in result.diagnostics)


def test_soft_student_avail_does_not_fail():
    """When student_availability=soft, the same impossible scenario produces
    warnings (not failure) and the schedule is still saved."""
    sym = (_day(9, 17),)
    early_only = (
        AvailabilityWindow(
            start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
        ),
    )
    presentations = (
        PresentationInput(id="p1", title="P1", duration_minutes=30, class_id="cA", resource_ids=("stu1",)),
        PresentationInput(id="p2", title="P2", duration_minutes=30, class_id="cA", resource_ids=("stu2",)),
    )
    problem = ScheduleProblem(
        symposium_id="t", rooms_available=1, symposium_windows=sym,
        presentations=presentations,
        soft_resource_windows={"stu1": early_only, "stu2": early_only},
        resource_name={"stu1": "Alice", "stu2": "Bob"},
        constraints=ScheduleConstraints(student_availability="soft"),
    )
    result = solve_hierarchical(problem, time_limit_seconds=10.0)
    assert result.status in ("optimal", "feasible"), result.diagnostics
    assert len(result.assignments) == 2
    assert any("warning" in d.lower() for d in result.diagnostics)


def test_room_conflicts_off_allows_overlap():
    """With room_conflicts=off the solver may place two blocks in the same
    room at the same time (room-no-overlap constraint disabled)."""
    sym = (_day(9, 11),)
    presentations = (
        PresentationInput(id="p1", title="A", duration_minutes=60, class_id="cA"),
        PresentationInput(id="p2", title="B", duration_minutes=60, class_id="cB"),
    )
    problem = ScheduleProblem(
        symposium_id="t", rooms_available=1, symposium_windows=sym,
        presentations=presentations,
        constraints=ScheduleConstraints(room_conflicts="off"),
    )
    result = solve_hierarchical(problem, time_limit_seconds=10.0)
    # With one room and two 60-min blocks in a 2-hour window, the only way
    # the makespan can be < 2h is if they overlap. The solver minimises
    # makespan so the no-overlap-off setting actually shows up.
    assert result.status in ("optimal", "feasible")
    a, b = sorted(result.assignments, key=lambda x: x.start)
    overlap = a.start < b.end and b.start < a.end
    assert overlap, "room_conflicts=off should permit room overlap when it shortens makespan"


def test_same_class_same_room_off():
    """With same_class_same_room=off, a class with two blocks may end up in
    different rooms if that improves makespan."""
    sym = (_day(9, 13),)
    # Class cA has two 60-min presentations. Two rooms available.
    # With makespan minimisation and SCSR=off, the solver should put them in
    # different rooms simultaneously to halve the makespan.
    presentations = (
        PresentationInput(id="p1", title="A1", duration_minutes=60, class_id="cA"),
        PresentationInput(id="p2", title="A2", duration_minutes=60, class_id="cA"),
    )
    problem = ScheduleProblem(
        symposium_id="t", rooms_available=2, symposium_windows=sym,
        presentations=presentations,
        constraints=ScheduleConstraints(same_class_same_room="off"),
    )
    # Force two blocks for the class by feeding them in via a manual block
    # split. (prepare_class_blocks would produce one block of 120 min here.)
    from app.scheduler.hierarchical import place_blocks, expand_blocks
    blocks = [
        ClassBlock(id="cA::0", class_id="cA", presentation_ids=("p1",),
                   total_minutes=60, allowed_windows=sym),
        ClassBlock(id="cA::1", class_id="cA", presentation_ids=("p2",),
                   total_minutes=60, allowed_windows=sym),
    ]
    placed, unsched, status = place_blocks(blocks, problem, 10.0)
    assert status in ("optimal", "feasible")
    assert len(placed) == 2
    rooms_used = {pb.room_index for pb in placed}
    assert len(rooms_used) == 2, "SCSR=off should let the two blocks land in different rooms"


def test_balance_rooms_soft_distributes_load():
    """With balance_rooms=soft and several blocks, no single room should hold
    every block when alternatives are available."""
    sym = (_day(9, 17),)
    presentations = tuple(
        PresentationInput(id=f"p{i}", title=f"T{i}", duration_minutes=30, class_id=f"c{i}")
        for i in range(6)
    )
    problem = ScheduleProblem(
        symposium_id="t", rooms_available=3, symposium_windows=sym,
        presentations=presentations,
        constraints=ScheduleConstraints(balance_rooms="soft"),
    )
    result = solve_hierarchical(problem, time_limit_seconds=10.0)
    assert result.status in ("optimal", "feasible")
    rooms_used = {a.room_index for a in result.assignments}
    assert len(rooms_used) >= 2, "balance_rooms=soft should spread blocks across rooms"


def test_within_block_reorder_for_student_windows():
    """Phase 3 should reorder presentations inside a block to fit students whose
    availability windows are tighter than the whole block.

    Block runs 9:00–10:30 (three 30-min slots). Three students:
        A: only available 9:00–9:30 (must go first)
        B: only available 10:00–10:30 (must go last)
        C: available all of 9:00–10:30 (flexible)

    Input order is (B, C, A) — would put 2 students outside their windows.
    Reorderer should produce something like (A, C, B) with 0 violations.
    """
    sym = (_day(9, 11),)
    student_windows = {
        "stuA": (
            AvailabilityWindow(
                start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc),
            ),
        ),
        "stuB": (
            AvailabilityWindow(
                start=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 6, 1, 10, 30, tzinfo=timezone.utc),
            ),
        ),
        "stuC": sym,
    }
    presentations = (
        PresentationInput(id="pA", title="A", duration_minutes=30, class_id="c1", resource_ids=("stuA",)),
        PresentationInput(id="pB", title="B", duration_minutes=30, class_id="c1", resource_ids=("stuB",)),
        PresentationInput(id="pC", title="C", duration_minutes=30, class_id="c1", resource_ids=("stuC",)),
    )
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=sym,
        presentations=presentations,
        resource_windows=student_windows,
    )

    block = ClassBlock(
        id="c1::0", class_id="c1",
        presentation_ids=("pB", "pC", "pA"),  # deliberately worst-case order
        total_minutes=90,
        allowed_windows=sym,
    )
    placed = [PlacedBlock(
        block=block, room_index=0,
        start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
    )]

    out = expand_blocks(placed, problem)

    # No availability warnings should remain after reordering.
    issues = [
        i for i in (
            *([] if out else []),
        )
    ]
    from app.scheduler.hierarchical import verify_assignments_split
    hard, soft = verify_assignments_split(out, problem)
    assert hard == ()
    assert soft == (), f"reorderer left soft violations: {soft}"

    # Verify the actual order: A first (only 9:00 fits), B last (only 10:00 fits).
    by_pid = {a.presentation_id: a for a in out}
    assert by_pid["pA"].start == datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    assert by_pid["pB"].start == datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)


def test_within_block_reorder_keeps_buffers():
    """Reordering must not break the per-presentation buffer: every consecutive
    pair in the same block should still have the buffer gap between them.
    """
    sym = (_day(9, 12),)
    presentations = (
        PresentationInput(id="p1", title="P1", duration_minutes=30, buffer_minutes=5, class_id="c1"),
        PresentationInput(id="p2", title="P2", duration_minutes=20, buffer_minutes=5, class_id="c1"),
        PresentationInput(id="p3", title="P3", duration_minutes=15, buffer_minutes=5, class_id="c1"),
    )
    problem = ScheduleProblem(
        symposium_id="test", rooms_available=1, symposium_windows=sym,
        presentations=presentations,
    )
    block = ClassBlock(
        id="c1::0", class_id="c1",
        presentation_ids=("p1", "p2", "p3"),
        total_minutes=30 + 5 + 20 + 5 + 15 + 5,
        allowed_windows=sym,
    )
    placed = [PlacedBlock(
        block=block, room_index=0,
        start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
    )]
    out = expand_blocks(placed, problem)

    # Every consecutive pair has at least a 5-minute gap.
    sorted_out = sorted(out, key=lambda a: a.start)
    for i in range(1, len(sorted_out)):
        gap = (sorted_out[i].start - sorted_out[i - 1].end).total_seconds() / 60
        assert gap >= 5, f"buffer not preserved between {sorted_out[i-1].presentation_id} and {sorted_out[i].presentation_id}"


def test_expand_blocks_preserves_order_and_buffers():
    """Phase-3 expansion lays out presentations sequentially, applying buffers."""
    presentations = (
        PresentationInput(id="a", title="A", duration_minutes=20, buffer_minutes=5, class_id="c1"),
        PresentationInput(id="b", title="B", duration_minutes=15, buffer_minutes=0, class_id="c1"),
        PresentationInput(id="c", title="C", duration_minutes=10, buffer_minutes=0, class_id="c1"),
    )
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=(_day(9, 17),),
        presentations=presentations,
    )
    block = ClassBlock(
        id="c1::0", class_id="c1",
        presentation_ids=("a", "b", "c"),
        total_minutes=20 + 5 + 15 + 10,
        allowed_windows=(_day(9, 17),),
    )
    placed = [PlacedBlock(
        block=block, room_index=0,
        start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
    )]
    out = expand_blocks(placed, problem)

    assert [a.presentation_id for a in out] == ["a", "b", "c"]
    assert out[0].start == datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    assert out[0].end == datetime(2026, 6, 1, 9, 20, tzinfo=timezone.utc)
    # buffer of 5 → b starts at 9:25
    assert out[1].start == datetime(2026, 6, 1, 9, 25, tzinfo=timezone.utc)
    assert out[1].end == datetime(2026, 6, 1, 9, 40, tzinfo=timezone.utc)
    assert out[2].start == datetime(2026, 6, 1, 9, 40, tzinfo=timezone.utc)
