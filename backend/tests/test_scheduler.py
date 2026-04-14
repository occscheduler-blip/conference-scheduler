import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.scheduler.cp_sat import solve_schedule
from app.scheduler.models import AvailabilityWindow, PresentationInput, ScheduleProblem


def test_basic_schedule():
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=45),
        ),
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2


def test_no_double_booking():
    """A resource shared across two presentations should not be scheduled at the same time."""
    windows = (
        AvailabilityWindow(
            start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
        ),
    )
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=windows,
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30, resource_ids=("prof1",)),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30, resource_ids=("prof1",)),
        ),
        resource_windows={"prof1": windows},
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2
    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")
    assert not (p1.start < p2.end and p2.start < p1.end), "Shared resource was double-booked"


def test_room_capacity():
    """More presentations than rooms should still be scheduled sequentially."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30),
            PresentationInput(id="p3", title="Talk 3", duration_minutes=30),
        ),
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 3
    for a in result.assignments:
        assert a.room_index == 0


def test_infeasible_no_availability():
    """A presentation with no valid time slots should return infeasible."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=60),
        ),
    )
    result = solve_schedule(problem)
    assert result.status == "infeasible"
    assert "p1" in result.unscheduled_presentations


def test_buffer_enforced():
    """A presentation with a 3-minute buffer must leave a 3-minute gap before the next one in the same room."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=1,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=10, buffer_minutes=3),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=10, buffer_minutes=0),
        ),
        slot_minutes=1,
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2

    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")

    # Determine which is first in the single room
    first, second = (p1, p2) if p1.start < p2.start else (p2, p1)
    gap = (second.start - first.end).total_seconds() / 60

    if first.presentation_id == "p1":
        # p1 (buffer=3) is first — gap must be at least 3 minutes
        assert gap >= 3, f"Expected gap >= 3 min after buffered presentation, got {gap:.1f} min"
    else:
        # p2 (buffer=0) is first — no gap required from p2, p1 follows
        # p1's buffer doesn't apply to what comes after p1 in this case;
        # just confirm the schedule is valid (no overlap)
        assert gap >= 0


def test_same_class_same_room():
    """All presentations from the same class must be assigned to the same room."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=30, class_id="class-A"),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=30, class_id="class-A"),
            PresentationInput(id="p3", title="Talk 3", duration_minutes=30, class_id="class-B"),
        ),
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 3

    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")
    assert p1.room_index == p2.room_index, (
        f"p1 and p2 share class-A but were placed in different rooms: {p1.room_index} vs {p2.room_index}"
    )


def test_buffer_with_same_class_room():
    """Presentations from the same class with a buffer should be sequential in one room with the correct gap."""
    problem = ScheduleProblem(
        symposium_id="test",
        rooms_available=2,
        symposium_windows=(
            AvailabilityWindow(
                start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
            ),
        ),
        presentations=(
            PresentationInput(id="p1", title="Talk 1", duration_minutes=10, buffer_minutes=3, class_id="class-A"),
            PresentationInput(id="p2", title="Talk 2", duration_minutes=10, buffer_minutes=3, class_id="class-A"),
        ),
        slot_minutes=1,
    )
    result = solve_schedule(problem)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2

    p1 = next(a for a in result.assignments if a.presentation_id == "p1")
    p2 = next(a for a in result.assignments if a.presentation_id == "p2")

    assert p1.room_index == p2.room_index, "Same-class presentations must be in the same room"

    first, second = (p1, p2) if p1.start < p2.start else (p2, p1)
    gap = (second.start - first.end).total_seconds() / 60
    assert gap >= 3, f"Expected gap >= 3 min between buffered same-class presentations, got {gap:.1f} min"


def test_large_schedule_timing():
    """20 presentations across 4 rooms with varied professors should solve within 10 seconds."""
    sym_windows = (
        AvailabilityWindow(
            start=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
        ),
    )

    # 10 professors each available for the full day
    num_professors = 10
    resource_windows = {
        f"prof{i}": sym_windows for i in range(num_professors)
    }

    # 20 presentations, each assigned to one professor
    presentations = tuple(
        PresentationInput(
            id=f"p{i}",
            title=f"Talk {i}",
            duration_minutes=30,
            resource_ids=(f"prof{i % num_professors}",),
        )
        for i in range(20)
    )

    problem = ScheduleProblem(
        symposium_id="test-large",
        rooms_available=4,
        symposium_windows=sym_windows,
        presentations=presentations,
        resource_windows=resource_windows,
    )

    start = time.perf_counter()
    result = solve_schedule(problem, time_limit_seconds=10.0)
    elapsed = time.perf_counter() - start

    assert result.status in ("optimal", "feasible"), f"Scheduler returned: {result.status}, diagnostics: {result.diagnostics}"
    assert len(result.assignments) == 20
    assert elapsed < 10.0, f"Scheduler took too long: {elapsed:.2f}s"
    print(f"\nLarge schedule solved in {elapsed:.2f}s")


# Removed for now because it takes way too long for a normal test run
# def test_massive_symposium():
#     """
#     200 presentations across a 3-day symposium with realistic complexity:

#     - 3 days (Jan 1–3), 8am–6pm each day, 8 rooms
#     - 15 professors, each with randomized availability (1–2 windows/day, some days off)
#     - 20 classes, each taught by one professor, each with 10 student presenters
#     - 1 presentation per student → 20 × 10 = 200 total presentations
#     - resource_ids per presentation = (professor, presenting_student)
#     - All presentations from the same class must share a room (same-class constraint)
#     - Presentation durations vary: 15, 20, or 25 minutes; 5-minute buffer between talks
#     - Fixed random seed for reproducibility
#     """
#     import random

#     rng = random.Random(42)

#     day_bounds = [
#         (datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc), datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc)),
#         (datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc), datetime(2024, 1, 2, 18, 0, tzinfo=timezone.utc)),
#         (datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc), datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)),
#     ]
#     sym_windows = tuple(AvailabilityWindow(start=s, end=e) for s, e in day_bounds)

#     def random_availability() -> tuple[AvailabilityWindow, ...]:
#         """
#         Generate 0–2 availability windows per day for a person.
#         Each window is at least 2 hours long. ~75% chance of being available on any given day.
#         Guarantees at least one window total so the person can be scheduled.
#         """
#         windows: list[AvailabilityWindow] = []
#         for day_start, day_end in day_bounds:
#             day_minutes = int((day_end - day_start).total_seconds() / 60)
#             num_windows = rng.choices([0, 1, 2], weights=[25, 55, 20])[0]
#             used: list[tuple[int, int]] = []
#             for _ in range(num_windows):
#                 for _attempt in range(10):
#                     s = rng.randint(0, day_minutes - 120)
#                     e = s + rng.randint(120, min(240, day_minutes - s))
#                     if all(e <= ws or s >= we for ws, we in used):
#                         used.append((s, e))
#                         windows.append(AvailabilityWindow(
#                             start=day_start + timedelta(minutes=s),
#                             end=day_start + timedelta(minutes=e),
#                         ))
#                         break
#         if not windows:
#             # Fallback: full first day so this person is always schedulable
#             windows.append(AvailabilityWindow(start=day_bounds[0][0], end=day_bounds[0][1]))
#         return tuple(windows)

#     NUM_PROFESSORS = 15
#     NUM_CLASSES = 20
#     STUDENTS_PER_CLASS = 10  # each student gives exactly one presentation → 200 total

#     resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}

#     for i in range(NUM_PROFESSORS):
#         resource_windows[f"prof{i}"] = random_availability()

#     presentations: list[PresentationInput] = []
#     pres_idx = 0
#     for c in range(NUM_CLASSES):
#         class_id = f"class{c}"
#         prof_id = f"prof{c % NUM_PROFESSORS}"
#         for s in range(STUDENTS_PER_CLASS):
#             student_id = f"student{c * STUDENTS_PER_CLASS + s}"
#             resource_windows[student_id] = random_availability()
#             presentations.append(PresentationInput(
#                 id=f"p{pres_idx}",
#                 title=f"Class {c} — Student {s}",
#                 duration_minutes=rng.choice([15, 20, 25]),
#                 buffer_minutes=5,
#                 class_id=class_id,
#                 resource_ids=(prof_id, student_id),
#             ))
#             pres_idx += 1

#     total = len(presentations)
#     assert total == NUM_CLASSES * STUDENTS_PER_CLASS  # 200

#     problem = ScheduleProblem(
#         symposium_id="test-massive",
#         rooms_available=8,
#         symposium_windows=sym_windows,
#         presentations=tuple(presentations),
#         resource_windows=resource_windows,
#     )

#     t0 = time.perf_counter()
#     result = solve_schedule(problem, time_limit_seconds=60.0)
#     elapsed = time.perf_counter() - t0

#     print(f"\nMassive symposium ({total} presentations) — status: {result.status} — {elapsed:.2f}s")
#     print(f"  Scheduled: {len(result.assignments)}, Unscheduled: {len(result.unscheduled_presentations)}")
#     for d in result.diagnostics:
#         print(f"  diagnostic: {d}")

#     assert result.status in ("optimal", "feasible"), (
#         f"Expected a partial schedule, got: {result.status}\n"
#         f"Diagnostics: {result.diagnostics}"
#     )
#     assert elapsed < 60.0, f"Solver exceeded time limit: {elapsed:.2f}s"

#     # At least 90% of presentations must be scheduled given the availability constraints
#     assert len(result.assignments) >= total * 0.90, (
#         f"Too many unscheduled: {len(result.unscheduled_presentations)} / {total}"
#     )

#     pres_by_id = {p.id: p for p in presentations}

#     # All same-class presentations must be in the same room
#     class_room: dict[str, int] = {}
#     for a in result.assignments:
#         cid = pres_by_id[a.presentation_id].class_id
#         if cid:
#             if cid in class_room:
#                 assert class_room[cid] == a.room_index, (
#                     f"Class {cid} split across rooms {class_room[cid]} and {a.room_index}"
#                 )
#             else:
#                 class_room[cid] = a.room_index

#     # No resource (professor or student) may be double-booked
#     resource_schedule: dict[str, list] = defaultdict(list)
#     for a in result.assignments:
#         for rid in pres_by_id[a.presentation_id].resource_ids:
#             resource_schedule[rid].append(a)
#     for rid, slots in resource_schedule.items():
#         slots.sort(key=lambda a: a.start)
#         for i in range(len(slots) - 1):
#             assert slots[i].end <= slots[i + 1].start, (
#                 f"Resource {rid} double-booked: "
#                 f"{slots[i].presentation_id} ({slots[i].start}–{slots[i].end}) overlaps "
#                 f"{slots[i + 1].presentation_id} ({slots[i + 1].start}–{slots[i + 1].end})"
#             )
