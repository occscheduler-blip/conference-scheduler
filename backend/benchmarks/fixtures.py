"""Programmatic ScheduleProblem builders.

Each builder returns a fully-formed `ScheduleProblem` plus a `FixtureMeta` with
the structural facts callers need (presentation count, prof count, expected
status, etc.) for verification and reporting.

No Supabase access. All randomness is seeded with `random.Random(<int>)` so
the same fixture name always produces the same problem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Callable

from app.scheduler.models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduleConstraints,
    ScheduleProblem,
)


@dataclass(frozen=True)
class FixtureMeta:
    """Structural facts about a generated fixture, used by verifiers/reporting.

    `expected_status` lets failure-mode fixtures declare what the solver should
    return — e.g. `"invalid"` for `no_rooms`, `"infeasible"` for `no_windows`.
    `None` means any of optimal/feasible is acceptable.
    """
    name: str
    presentations: int
    professors: int
    students: int
    classes: int
    departments: int
    rooms: int
    days: int
    expected_status: str | None = None
    notes: str = ""
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Fixture:
    problem: ScheduleProblem
    meta: FixtureMeta


# ── Availability generation ───────────────────────────────────────────────


def _random_availability(
    rng: Random,
    day_bounds: list[tuple[datetime, datetime]],
    coverage: float,
    max_windows_per_day: int = 3,
    min_window_minutes: int = 60,
) -> tuple[AvailabilityWindow, ...]:
    """Generate availability windows whose total length ≈ coverage × day length.

    Mirrors the seed-script algorithm. `coverage=1.0` returns the whole day in
    one window.
    """
    windows: list[AvailabilityWindow] = []
    for day_start, day_end in day_bounds:
        day_minutes = int((day_end - day_start).total_seconds() / 60)
        target = max(min_window_minutes, min(day_minutes, round(day_minutes * coverage)))
        max_wins = min(max_windows_per_day, target // min_window_minutes)
        if max_wins < 1:
            continue
        weights = [50, 35, 15][:max_wins]
        num_windows = rng.choices(range(1, max_wins + 1), weights=weights)[0]
        placed: list[tuple[int, int]] = []
        remaining = target
        for w in range(num_windows):
            wins_left = num_windows - w
            min_len = min_window_minutes
            max_len = remaining - min_len * (wins_left - 1)
            if max_len < min_len:
                break
            win_len = rng.randint(min_len, max_len)
            for _ in range(20):
                s = rng.randint(0, day_minutes - win_len)
                e = s + win_len
                if all(e <= ws or s >= we for ws, we in placed):
                    placed.append((s, e))
                    windows.append(
                        AvailabilityWindow(
                            start=day_start + timedelta(minutes=s),
                            end=day_start + timedelta(minutes=e),
                        )
                    )
                    remaining -= win_len
                    break
    if not windows:
        windows.append(AvailabilityWindow(start=day_bounds[0][0], end=day_bounds[0][1]))
    windows.sort(key=lambda w: w.start)
    return tuple(windows)


def _full_day_windows(
    day_bounds: list[tuple[datetime, datetime]],
) -> tuple[AvailabilityWindow, ...]:
    return tuple(AvailabilityWindow(start=s, end=e) for s, e in day_bounds)


# ── Scale fixtures ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ScaleConfig:
    name: str
    professors: int
    classes: int
    students_per_class: int
    departments: int
    rooms: int
    days: int
    day_hours: int
    day_start_hour: int
    coverage_low: float
    coverage_high: float
    coverage_mode: float
    seed: int


def _build_scale(cfg: _ScaleConfig) -> Fixture:
    rng = Random(cfg.seed)

    base_date = datetime(2030, 4, 15, cfg.day_start_hour, 0, tzinfo=timezone.utc)
    day_bounds = [
        (
            base_date + timedelta(days=d),
            base_date + timedelta(days=d, hours=cfg.day_hours),
        )
        for d in range(cfg.days)
    ]
    sym_windows = _full_day_windows(day_bounds)

    def coverage() -> float:
        return rng.triangular(cfg.coverage_low, cfg.coverage_high, cfg.coverage_mode)

    department_ids = [f"dept-{cfg.name}-{i}" for i in range(cfg.departments)]

    professor_ids = [f"prof-{cfg.name}-{i}" for i in range(cfg.professors)]
    professor_windows = {
        pid: _random_availability(rng, day_bounds, coverage()) for pid in professor_ids
    }

    class_to_dept: dict[str, str] = {}
    class_to_prof: dict[str, str] = {}
    class_ids: list[str] = []
    for c in range(cfg.classes):
        cid = f"class-{cfg.name}-{c}"
        class_ids.append(cid)
        class_to_dept[cid] = department_ids[c % cfg.departments]
        class_to_prof[cid] = professor_ids[c % cfg.professors]

    presentations: list[PresentationInput] = []
    student_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}
    resource_name: dict[str, str] = {pid: f"Professor {i}" for i, pid in enumerate(professor_ids)}

    for c, cid in enumerate(class_ids):
        for s in range(cfg.students_per_class):
            sid = f"student-{cfg.name}-{c}-{s}"
            student_windows[sid] = _random_availability(rng, day_bounds, coverage())
            resource_name[sid] = f"Student {c}-{s}"
            duration = rng.choice([15, 20, 25])
            presentations.append(
                PresentationInput(
                    id=f"pres-{cfg.name}-{c}-{s}",
                    title=f"{cfg.name} c{c} s{s}",
                    duration_minutes=duration,
                    buffer_minutes=5,
                    class_id=cid,
                    department_id=class_to_dept[cid],
                    resource_ids=(class_to_prof[cid], sid),
                )
            )

    constraints = ScheduleConstraints()  # defaults

    # Per service.py default: professor windows are hard, student windows are soft.
    resource_windows = dict(professor_windows)
    soft_resource_windows = dict(student_windows)

    problem = ScheduleProblem(
        symposium_id=f"sym-{cfg.name}",
        rooms_available=cfg.rooms,
        symposium_windows=sym_windows,
        presentations=tuple(presentations),
        resource_windows=resource_windows,
        soft_resource_windows=soft_resource_windows,
        professor_resource_ids=tuple(professor_ids),
        resource_identity={k: k for k in (*professor_ids, *student_windows.keys())},
        resource_name=resource_name,
        slot_minutes=5,
        constraints=constraints,
    )

    meta = FixtureMeta(
        name=cfg.name,
        presentations=len(presentations),
        professors=cfg.professors,
        students=len(student_windows),
        classes=cfg.classes,
        departments=cfg.departments,
        rooms=cfg.rooms,
        days=cfg.days,
        expected_status=None,
    )
    return Fixture(problem=problem, meta=meta)


def fixture_tiny() -> Fixture:
    return _build_scale(
        _ScaleConfig(
            name="tiny",
            professors=1,
            classes=1,
            students_per_class=5,
            departments=1,
            rooms=1,
            days=1,
            day_hours=5,
            day_start_hour=13,
            coverage_low=0.8,
            coverage_high=1.0,
            coverage_mode=0.95,
            seed=1,
        )
    )


def fixture_small() -> Fixture:
    return _build_scale(
        _ScaleConfig(
            name="small",
            professors=3,
            classes=3,
            students_per_class=4,
            departments=1,
            rooms=2,
            days=1,
            day_hours=5,
            day_start_hour=13,
            coverage_low=0.6,
            coverage_high=1.0,
            coverage_mode=0.8,
            seed=7,
        )
    )


def fixture_medium() -> Fixture:
    return _build_scale(
        _ScaleConfig(
            name="medium",
            professors=6,
            classes=8,
            students_per_class=6,
            departments=2,
            rooms=4,
            days=2,
            day_hours=7,
            day_start_hour=13,
            coverage_low=0.55,
            coverage_high=1.0,
            coverage_mode=0.75,
            seed=13,
        )
    )


def fixture_large() -> Fixture:
    return _build_scale(
        _ScaleConfig(
            name="large",
            professors=10,
            classes=10,
            students_per_class=10,
            departments=3,
            rooms=6,
            days=3,
            day_hours=8,
            day_start_hour=13,
            coverage_low=0.5,
            coverage_high=1.0,
            coverage_mode=0.7,
            seed=23,
        )
    )


def fixture_massive() -> Fixture:
    return _build_scale(
        _ScaleConfig(
            name="massive",
            professors=15,
            classes=20,
            students_per_class=10,
            departments=4,
            rooms=8,
            days=3,
            day_hours=9,
            day_start_hour=12,
            coverage_low=0.5,
            coverage_high=1.0,
            coverage_mode=0.75,
            seed=42,
        )
    )


def fixture_huge() -> Fixture:
    return _build_scale(
        _ScaleConfig(
            name="huge",
            professors=25,
            classes=40,
            students_per_class=10,
            departments=6,
            rooms=12,
            days=4,
            day_hours=10,
            day_start_hour=12,
            coverage_low=0.5,
            coverage_high=1.0,
            coverage_mode=0.75,
            seed=99,
        )
    )


# ── Failure-mode fixtures ─────────────────────────────────────────────────


def fixture_prof_bottleneck() -> Fixture:
    """Prof window shorter than presentation duration → all unschedulable."""
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 11, 0, tzinfo=timezone.utc)
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    prof_id = "prof-narrow"
    # 15-minute window — smaller than any 20-minute presentation.
    prof_windows = (
        AvailabilityWindow(
            start=sym_start, end=sym_start + timedelta(minutes=15)
        ),
    )
    presentations = tuple(
        PresentationInput(
            id=f"pres-narrow-{i}",
            title=f"Bottleneck {i}",
            duration_minutes=20,
            buffer_minutes=5,
            class_id="class-narrow",
            department_id="dept-narrow",
            resource_ids=(prof_id,),
        )
        for i in range(3)
    )
    problem = ScheduleProblem(
        symposium_id="sym-bottleneck",
        rooms_available=2,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows={prof_id: prof_windows},
        professor_resource_ids=(prof_id,),
        resource_name={prof_id: "Dr. Narrow"},
    )
    meta = FixtureMeta(
        name="prof-bottleneck",
        presentations=3,
        professors=1,
        students=0,
        classes=1,
        departments=1,
        rooms=2,
        days=1,
        expected_status="infeasible",
        notes="All presentations should fail pre-filter.",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_class_crunch() -> Fixture:
    """Same-class room time required > any contiguous symposium window.

    5 × 25-minute presentations with 5-min buffers in one class need 150 min of
    contiguous room time. Symposium window is 120 min. With same_class_same_room
    hard, at least one presentation must be unscheduled.
    """
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = sym_start + timedelta(minutes=120)
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    prof_id = "prof-full"
    prof_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    presentations = tuple(
        PresentationInput(
            id=f"pres-crunch-{i}",
            title=f"Crunch {i}",
            duration_minutes=25,
            buffer_minutes=5,
            class_id="class-crunch",
            department_id="dept-crunch",
            resource_ids=(prof_id,),
        )
        for i in range(5)
    )
    problem = ScheduleProblem(
        symposium_id="sym-crunch",
        rooms_available=2,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows={prof_id: prof_windows},
        professor_resource_ids=(prof_id,),
        resource_name={prof_id: "Dr. Full"},
    )
    meta = FixtureMeta(
        name="class-crunch",
        presentations=5,
        professors=1,
        students=0,
        classes=1,
        departments=1,
        rooms=2,
        days=1,
        # CP-SAT may schedule 4/5; we accept feasible-with-unscheduled.
        expected_status=None,
        notes="At least 1 presentation must be unscheduled (same-class-same-room hard).",
        extra={"min_unscheduled": 1},
    )
    return Fixture(problem=problem, meta=meta)


def fixture_prof_student_gap() -> Fixture:
    """Professor and student windows never overlap → unschedulable."""
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 11, 0, tzinfo=timezone.utc)
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    prof_id = "prof-morning"
    prof_windows = (AvailabilityWindow(start=sym_start, end=sym_start + timedelta(hours=1)),)

    student_a = "student-late-a"
    student_b = "student-late-b"
    late_start = sym_start + timedelta(minutes=90)
    late_end = sym_end
    student_windows = {
        student_a: (AvailabilityWindow(start=late_start, end=late_end),),
        student_b: (AvailabilityWindow(start=late_start, end=late_end),),
    }

    presentations = (
        PresentationInput(
            id="pres-gap-a",
            title="Gap A",
            duration_minutes=20,
            class_id="class-gap",
            department_id="dept-gap",
            resource_ids=(prof_id, student_a),
        ),
        PresentationInput(
            id="pres-gap-b",
            title="Gap B",
            duration_minutes=20,
            class_id="class-gap",
            department_id="dept-gap",
            resource_ids=(prof_id, student_b),
        ),
    )

    # Student availability is hard here so the gap is exposed; default would be
    # soft and the solver would ignore the gap with a penalty.
    constraints = ScheduleConstraints(student_availability="hard")

    problem = ScheduleProblem(
        symposium_id="sym-gap",
        rooms_available=1,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows={prof_id: prof_windows, **student_windows},
        professor_resource_ids=(prof_id,),
        resource_name={prof_id: "Dr. Morning", student_a: "Late A", student_b: "Late B"},
        constraints=constraints,
    )
    meta = FixtureMeta(
        name="prof-student-gap",
        presentations=2,
        professors=1,
        students=2,
        classes=1,
        departments=1,
        rooms=1,
        days=1,
        expected_status="infeasible",
        notes="Prof and student windows never overlap.",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_no_rooms() -> Fixture:
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 17, 0, tzinfo=timezone.utc)
    problem = ScheduleProblem(
        symposium_id="sym-no-rooms",
        rooms_available=0,
        symposium_windows=(AvailabilityWindow(start=sym_start, end=sym_end),),
        presentations=(
            PresentationInput(id="p1", title="x", duration_minutes=15),
        ),
    )
    meta = FixtureMeta(
        name="no-rooms",
        presentations=1, professors=0, students=0, classes=0, departments=0,
        rooms=0, days=1,
        expected_status="invalid",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_no_windows() -> Fixture:
    problem = ScheduleProblem(
        symposium_id="sym-no-windows",
        rooms_available=2,
        symposium_windows=(),
        presentations=(
            PresentationInput(id="p1", title="x", duration_minutes=15),
        ),
    )
    meta = FixtureMeta(
        name="no-windows",
        presentations=1, professors=0, students=0, classes=0, departments=0,
        rooms=2, days=0,
        expected_status="infeasible",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_no_presentations() -> Fixture:
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 17, 0, tzinfo=timezone.utc)
    problem = ScheduleProblem(
        symposium_id="sym-no-pres",
        rooms_available=2,
        symposium_windows=(AvailabilityWindow(start=sym_start, end=sym_end),),
        presentations=(),
    )
    meta = FixtureMeta(
        name="no-presentations",
        presentations=0, professors=0, students=0, classes=0, departments=0,
        rooms=2, days=1,
        expected_status="optimal",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_oversubscribed() -> Fixture:
    """rooms × time < required time → forced partial result."""
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 11, 0, tzinfo=timezone.utc)  # 120 min
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    # 12 × 30-min presentations = 360 min. 1 room × 120 min = 120 min available.
    # Solver should fit ~4 and report 8 unscheduled.
    presentations = tuple(
        PresentationInput(
            id=f"pres-over-{i}",
            title=f"Over {i}",
            duration_minutes=30,
            class_id=f"class-over-{i}",  # all different classes — same_class_same_room not binding
            department_id="dept-over",
        )
        for i in range(12)
    )
    problem = ScheduleProblem(
        symposium_id="sym-over",
        rooms_available=1,
        symposium_windows=sym_windows,
        presentations=presentations,
    )
    meta = FixtureMeta(
        name="oversubscribed",
        presentations=12, professors=0, students=0, classes=12, departments=1,
        rooms=1, days=1,
        expected_status=None,
        notes="At most 4 should schedule (120 min / 30 min); ≥8 unscheduled.",
        extra={"min_unscheduled": 8},
    )
    return Fixture(problem=problem, meta=meta)


def fixture_cross_listed_prof() -> Fixture:
    """Same prof identity (email) registered under two row-ids in two classes.

    Tests resource_identity dedup: even though row-id-A and row-id-B are
    different, they map to the same canonical key, so the solver must not
    schedule a class-A presentation overlapping a class-B presentation.
    """
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 13, 0, tzinfo=timezone.utc)
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    prof_row_a = "prof-row-a"
    prof_row_b = "prof-row-b"
    prof_canonical = "prof@hamilton.edu"

    full_window = (AvailabilityWindow(start=sym_start, end=sym_end),)

    presentations = tuple(
        PresentationInput(
            id=f"pres-xlist-{c}-{i}",
            title=f"XList c{c} i{i}",
            duration_minutes=30,
            buffer_minutes=0,
            class_id=f"class-xlist-{c}",
            department_id="dept-xlist",
            resource_ids=(prof_row_a if c == 0 else prof_row_b,),
        )
        for c in range(2)
        for i in range(3)
    )
    problem = ScheduleProblem(
        symposium_id="sym-xlist",
        rooms_available=2,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows={prof_row_a: full_window, prof_row_b: full_window},
        professor_resource_ids=(prof_row_a, prof_row_b),
        resource_identity={prof_row_a: prof_canonical, prof_row_b: prof_canonical},
        resource_name={prof_row_a: "Cross-Listed Prof", prof_row_b: "Cross-Listed Prof"},
    )
    meta = FixtureMeta(
        name="cross-listed-prof",
        presentations=6, professors=1, students=0, classes=2, departments=1,
        rooms=2, days=1,
        expected_status=None,
        notes="Tests resource_identity dedup: prof must not appear in two rooms at once.",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_double_major_student() -> Fixture:
    """Same student under two row-ids in two classes — same identity dedup."""
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = datetime(2030, 5, 20, 13, 0, tzinfo=timezone.utc)
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)

    prof_a = "prof-dm-a"
    prof_b = "prof-dm-b"
    student_row_a = "student-row-a"
    student_row_b = "student-row-b"
    student_canonical = "student@hamilton.edu"

    full_window = (AvailabilityWindow(start=sym_start, end=sym_end),)

    presentations = (
        PresentationInput(
            id="pres-dm-a", title="DM A",
            duration_minutes=30, class_id="class-dm-a", department_id="dept-dm",
            resource_ids=(prof_a, student_row_a),
        ),
        PresentationInput(
            id="pres-dm-b", title="DM B",
            duration_minutes=30, class_id="class-dm-b", department_id="dept-dm",
            resource_ids=(prof_b, student_row_b),
        ),
    )
    problem = ScheduleProblem(
        symposium_id="sym-dm",
        rooms_available=2,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows={
            prof_a: full_window, prof_b: full_window,
        },
        soft_resource_windows={
            student_row_a: full_window, student_row_b: full_window,
        },
        professor_resource_ids=(prof_a, prof_b),
        resource_identity={
            prof_a: prof_a, prof_b: prof_b,
            student_row_a: student_canonical,
            student_row_b: student_canonical,
        },
        resource_name={
            prof_a: "Prof A", prof_b: "Prof B",
            student_row_a: "Double-Major Student", student_row_b: "Double-Major Student",
        },
    )
    meta = FixtureMeta(
        name="double-major-student",
        presentations=2, professors=2, students=1, classes=2, departments=1,
        rooms=2, days=1,
        expected_status=None,
        notes="Same student in two classes via resource_identity.",
    )
    return Fixture(problem=problem, meta=meta)


def fixture_tight_feasibility() -> Fixture:
    """Exactly enough room-time to fit everything — solver must find the packing.

    1 room × 200 min, 10 × 20-min presentations, no buffers, no other
    constraints. Any imperfect packing leaves a presentation unscheduled.
    """
    sym_start = datetime(2030, 5, 20, 9, 0, tzinfo=timezone.utc)
    sym_end = sym_start + timedelta(minutes=200)
    sym_windows = (AvailabilityWindow(start=sym_start, end=sym_end),)
    presentations = tuple(
        PresentationInput(
            id=f"pres-tight-{i}",
            title=f"Tight {i}",
            duration_minutes=20,
            buffer_minutes=0,
            class_id=f"class-tight-{i}",
            department_id="dept-tight",
        )
        for i in range(10)
    )
    problem = ScheduleProblem(
        symposium_id="sym-tight",
        rooms_available=1,
        symposium_windows=sym_windows,
        presentations=presentations,
    )
    meta = FixtureMeta(
        name="tight-feasibility",
        presentations=10, professors=0, students=0, classes=10, departments=1,
        rooms=1, days=1,
        expected_status=None,
        notes="Exactly fits — all 10 must schedule.",
        extra={"required_scheduled": 10},
    )
    return Fixture(problem=problem, meta=meta)


# ── Sweep variants ────────────────────────────────────────────────────────


def fixture_medium_with_coverage(coverage_mode: float, label: str) -> Fixture:
    """Medium fixture with a tunable coverage_mode for the loose-vs-tight sweep."""
    fix = _build_scale(
        _ScaleConfig(
            name=f"medium-cov-{label}",
            professors=6, classes=8, students_per_class=6,
            departments=2, rooms=4, days=2, day_hours=7, day_start_hour=13,
            coverage_low=max(0.4, coverage_mode - 0.2),
            coverage_high=min(1.0, coverage_mode + 0.2),
            coverage_mode=coverage_mode,
            seed=13,
        )
    )
    return fix


def fixture_medium_with_slot(slot_minutes: int) -> Fixture:
    fix = fixture_medium()
    new_problem = ScheduleProblem(
        symposium_id=fix.problem.symposium_id,
        rooms_available=fix.problem.rooms_available,
        symposium_windows=fix.problem.symposium_windows,
        presentations=fix.problem.presentations,
        resource_windows=fix.problem.resource_windows,
        soft_resource_windows=fix.problem.soft_resource_windows,
        professor_resource_ids=fix.problem.professor_resource_ids,
        resource_identity=fix.problem.resource_identity,
        resource_name=fix.problem.resource_name,
        slot_minutes=slot_minutes,
        constraints=fix.problem.constraints,
    )
    new_meta = FixtureMeta(
        **{**fix.meta.__dict__, "name": f"medium-slot-{slot_minutes}"}
    )
    return Fixture(problem=new_problem, meta=new_meta)


def fixture_medium_with_constraints(
    *,
    student_availability: str = "soft",
    same_class_same_room: str = "hard",
    label: str = "default",
) -> Fixture:
    fix = fixture_medium()
    new_constraints = ScheduleConstraints(
        room_conflicts="hard",
        person_conflicts="hard",
        symposium_windows="hard",
        professor_availability="hard",
        student_availability=student_availability,  # type: ignore[arg-type]
        same_class_same_room=same_class_same_room,  # type: ignore[arg-type]
    )
    # When student_availability flips between soft/hard, move student windows
    # between resource_windows and soft_resource_windows accordingly.
    if student_availability == "hard":
        new_resource_windows = {**fix.problem.resource_windows, **fix.problem.soft_resource_windows}
        new_soft_resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}
    else:
        new_resource_windows = dict(fix.problem.resource_windows)
        new_soft_resource_windows = dict(fix.problem.soft_resource_windows)

    new_problem = ScheduleProblem(
        symposium_id=fix.problem.symposium_id,
        rooms_available=fix.problem.rooms_available,
        symposium_windows=fix.problem.symposium_windows,
        presentations=fix.problem.presentations,
        resource_windows=new_resource_windows,
        soft_resource_windows=new_soft_resource_windows,
        professor_resource_ids=fix.problem.professor_resource_ids,
        resource_identity=fix.problem.resource_identity,
        resource_name=fix.problem.resource_name,
        slot_minutes=fix.problem.slot_minutes,
        constraints=new_constraints,
    )
    new_meta = FixtureMeta(
        **{**fix.meta.__dict__, "name": f"medium-constraints-{label}"}
    )
    return Fixture(problem=new_problem, meta=new_meta)


# ── Registry ──────────────────────────────────────────────────────────────


FIXTURE_BUILDERS: dict[str, Callable[[], Fixture]] = {
    # Scale
    "tiny": fixture_tiny,
    "small": fixture_small,
    "medium": fixture_medium,
    "large": fixture_large,
    "massive": fixture_massive,
    "huge": fixture_huge,
    # Failure modes
    "prof-bottleneck": fixture_prof_bottleneck,
    "class-crunch": fixture_class_crunch,
    "prof-student-gap": fixture_prof_student_gap,
    "no-rooms": fixture_no_rooms,
    "no-windows": fixture_no_windows,
    "no-presentations": fixture_no_presentations,
    "oversubscribed": fixture_oversubscribed,
    "cross-listed-prof": fixture_cross_listed_prof,
    "double-major-student": fixture_double_major_student,
    "tight-feasibility": fixture_tight_feasibility,
}
