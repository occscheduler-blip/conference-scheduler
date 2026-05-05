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

    t0 = time.perf_counter()
    result = solve_hierarchical(problem, time_limit_seconds=30.0)
    elapsed = time.perf_counter() - t0

    assert result.status in ("optimal", "feasible"), f"got {result.status} diags={result.diagnostics}"
    assert len(result.assignments) == 400
    assert elapsed < 30.0, f"hierarchical solve took {elapsed:.1f}s"

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
