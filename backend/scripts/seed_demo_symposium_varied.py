"""
Seed script: deterministic demo symposium with VARIED availabilities.

The companion to ``seed_demo_symposium.py``. The structural shape is
identical (10 departments, 43 classes, 356 presentations, same group
sizes and durations) so the two demos are directly comparable, but
this script rotates through a much wider menu of availability shapes
for both professors and presentations: whole-day, morning-only,
afternoon-only, midday, early, late, and three split-day patterns.

Two design rules keep the symposium fully solvable despite the variety:

  1. Professor shapes are always made of whole days. Presentation
     shapes always include at least one window on every day. Their
     intersection is therefore non-empty for any combination.
  2. All members of a presentation share the presentation's
     availability windows, so a group never has an empty intersection
     among its own members.

Single-day professor shapes are bumped up to ``full`` for large
classes (≥ 9 presentations) so the prof always has enough hours to
cover their roster.

Re-runs are idempotent: the previously seeded varied-availability
demo symposium is deleted first (by its stable UUID) before fresh
data is inserted.

Run from the backend directory:
    python scripts/seed_demo_symposium_varied.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from supabase import create_client

from app.supabase_io.delete import delete_symposium  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Deterministic UUIDs
# ---------------------------------------------------------------------------
# Different namespace from ``seed_demo_symposium.py`` so both demo symposia
# can live in the same DB simultaneously without ID collisions.

VARIED_NS = uuid.UUID("a55ec5cb-a55e-c5cb-a55e-c5cba55ec5cb")


def det_id(*parts: object) -> str:
    return str(uuid.uuid5(VARIED_NS, ":".join(str(p) for p in parts)))


# ---------------------------------------------------------------------------
# Symposium configuration
# ---------------------------------------------------------------------------

SYMPOSIUM_NAME = "Hamilton Spring 2026 Demo Symposium (Varied Availability)"
ROOMS_AVAILABLE = 10
DEFAULT_BUFFER = 5

# Same 3-day window as the baseline demo: 9 AM – 5 PM UTC.
DAY_BOUNDS: list[tuple[datetime, datetime]] = [
    (datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
     datetime(2026, 5, 11, 17, 0, tzinfo=timezone.utc)),
    (datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
     datetime(2026, 5, 12, 17, 0, tzinfo=timezone.utc)),
    (datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
     datetime(2026, 5, 13, 17, 0, tzinfo=timezone.utc)),
]

CREATED_AT = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()


# Identical department / class layout to ``seed_demo_symposium.py`` so the
# two demos are directly comparable; the only intentional difference is in
# the availability data.
DEPARTMENTS: list[tuple[str, str, list[tuple[str, int]]]] = [
    ("Computer Science", "Eleanor Mason", [
        ("CS 101 Intro to Programming",   14),
        ("CS 201 Data Structures",        12),
        ("CS 301 Algorithms",             10),
        ("CS 350 Operating Systems",       9),
        ("CS 401 Machine Learning",        8),
        ("CS 410 Computer Graphics",       7),
        ("CS 420 Distributed Systems",     6),
        ("CS 490 Senior Capstone",         4),
    ]),
    ("Biology", "Marcus Whitfield", [
        ("BIO 101 General Biology",       16),
        ("BIO 220 Genetics",              13),
        ("BIO 310 Microbiology",          11),
        ("BIO 340 Ecology",                9),
        ("BIO 410 Neurobiology",           7),
        ("BIO 430 Marine Biology",         5),
        ("BIO 490 Senior Research",        4),
    ]),
    ("Mathematics", "Hannah Liu", [
        ("MATH 101 Calculus I",           12),
        ("MATH 201 Linear Algebra",       10),
        ("MATH 310 Real Analysis",         8),
        ("MATH 350 Topology",              6),
        ("MATH 410 Number Theory",         5),
    ]),
    ("English Literature", "Theodora Patel", [
        ("ENG 101 Composition",           14),
        ("ENG 220 Shakespeare",           11),
        ("ENG 300 Modern Poetry",          8),
        ("ENG 350 Postcolonial Lit",       6),
        ("ENG 410 Literary Theory",        4),
    ]),
    ("History", "Samuel Okafor", [
        ("HIST 101 World History",        13),
        ("HIST 220 American History",     10),
        ("HIST 310 European History",      7),
        ("HIST 410 Asian Studies",         5),
    ]),
    ("Physics", "Priya Ramanathan", [
        ("PHYS 101 Mechanics",            12),
        ("PHYS 220 Electromagnetism",      9),
        ("PHYS 410 Quantum Mechanics",     6),
    ]),
    ("Economics", "Joaquin Vega", [
        ("ECON 101 Microeconomics",       11),
        ("ECON 201 Macroeconomics",        9),
        ("ECON 310 Game Theory",           7),
        ("ECON 410 Econometrics",          4),
    ]),
    ("Psychology", "Aisha Nordstrom", [
        ("PSYC 101 Intro to Psych",       10),
        ("PSYC 220 Cognitive Psych",       8),
        ("PSYC 310 Clinical Psych",        6),
        ("PSYC 410 Neuroscience",          4),
    ]),
    ("Art History", "Rosalind Bekov", [
        ("ARTH 101 Renaissance Art",       6),
        ("ARTH 310 Modern Art",            4),
    ]),
    ("Philosophy", "Aurelius Tan", [
        ("PHIL 220 Ethics",                6),
    ]),
]

GROUP_SIZE_CYCLE = [1, 1, 1, 2, 1, 3, 1, 1, 2, 1]
DURATION_CYCLE = [20, 15, 20, 25, 20, 10, 20, 30, 20, 20, 15, 25]

FIRST_NAMES = [
    "Adam", "Beatrice", "Carlos", "Diana", "Ethan", "Fiona", "Gabriel", "Hana",
    "Isaac", "Jasmine", "Kenji", "Lila", "Mateo", "Nora", "Omar", "Penelope",
    "Quentin", "Riya", "Soren", "Talia", "Ulysses", "Vera", "Wesley", "Xiomara",
    "Yusuf", "Zara",
]
LAST_NAMES = [
    "Anderson", "Brooks", "Chen", "Diaz", "Edwards", "Fischer", "Gupta",
    "Hayes", "Iversen", "Johansson", "Khan", "Lopez", "Murphy", "Nakamura",
    "OConnor", "Patel", "Quinones", "Rivera", "Saito", "Tanaka", "Underwood",
    "Vasquez", "Williams", "Xu", "Young", "Zimmerman",
]


# ---------------------------------------------------------------------------
# Availability shapes
# ---------------------------------------------------------------------------
# Two menus designed so that any (professor shape, presentation shape) pair
# has a non-empty time intersection:
#   - PROFESSOR_SHAPES contain whole symposium days, possibly fewer than 3.
#   - PRESENTATION_SHAPES always include some window on every symposium day.
# Whole day ∩ partial-window-on-that-day = the partial window, which is
# always at least 2 hours.

ShapeFn = Callable[[], list[tuple[datetime, datetime]]]


def _full() -> list[tuple[datetime, datetime]]:
    return list(DAY_BOUNDS)


def _day(i: int) -> list[tuple[datetime, datetime]]:
    return [DAY_BOUNDS[i]]


def _days(*indices: int) -> list[tuple[datetime, datetime]]:
    return [DAY_BOUNDS[i] for i in indices]


def _per_day(start_h: int, end_h: int) -> list[tuple[datetime, datetime]]:
    """Same offset-from-day-start window applied to every symposium day."""
    return [
        (s + timedelta(hours=start_h), s + timedelta(hours=end_h))
        for s, _ in DAY_BOUNDS
    ]


PROFESSOR_SHAPES: dict[str, ShapeFn] = {
    "full":      _full,
    "days_1_2":  lambda: _days(0, 1),
    "days_2_3":  lambda: _days(1, 2),
    "days_1_3":  lambda: _days(0, 2),
    "day1":      lambda: _day(0),
    "day2":      lambda: _day(1),
    "day3":      lambda: _day(2),
}

PRESENTATION_SHAPES: dict[str, ShapeFn] = {
    "full":       _full,
    "morning":    lambda: _per_day(0, 3),    # 9–12 each day
    "afternoon":  lambda: _per_day(4, 8),    # 13–17 each day
    "midday":     lambda: _per_day(2, 6),    # 11–15 each day
    "early":      lambda: _per_day(0, 2),    # 9–11 each day
    "late":       lambda: _per_day(6, 8),    # 15–17 each day
    "split_a":    lambda: [
        (DAY_BOUNDS[0][0], DAY_BOUNDS[0][0] + timedelta(hours=3)),    # d1 9–12
        (DAY_BOUNDS[1][1] - timedelta(hours=4), DAY_BOUNDS[1][1]),    # d2 13–17
        (DAY_BOUNDS[2][0], DAY_BOUNDS[2][0] + timedelta(hours=3)),    # d3 9–12
    ],
    "split_b":    lambda: [
        DAY_BOUNDS[0],                                                # d1 full
        (DAY_BOUNDS[1][0], DAY_BOUNDS[1][0] + timedelta(hours=3)),    # d2 9–12
        (DAY_BOUNDS[2][1] - timedelta(hours=4), DAY_BOUNDS[2][1]),    # d3 13–17
    ],
    "split_c":    lambda: [
        (DAY_BOUNDS[0][1] - timedelta(hours=4), DAY_BOUNDS[0][1]),    # d1 13–17
        (DAY_BOUNDS[1][0], DAY_BOUNDS[1][0] + timedelta(hours=3)),    # d2 9–12
        DAY_BOUNDS[2],                                                # d3 full
    ],
}


# Cycles. Tuned so "full" appears often enough to keep the schedule
# comfortable, with the rest spread across the more restricted shapes.
PROFESSOR_AVAIL_CYCLE = [
    "full", "full", "days_1_2", "full", "days_2_3",
    "full", "days_1_3", "full", "day2", "full",
    "days_1_2", "day3", "full", "days_2_3", "day1",
]

PRESENTATION_AVAIL_CYCLE = [
    "full", "morning", "full", "afternoon", "full",
    "midday", "split_a", "full", "early", "afternoon",
    "full", "late", "morning", "split_b", "full",
    "afternoon", "midday", "split_c", "full", "morning",
    "full", "early", "late", "afternoon", "morning",
]


# A single-day professor only has 8 hours. With 5-min buffers and ~25 min
# average presentation length that is enough for ~16 talks back-to-back —
# but the schedule also has to honor student windows, so leave headroom by
# bumping single-day shapes to "full" for any class with this many or more
# presentations.
PROF_FULL_DAY_THRESHOLD = 9


def professor_shape_name(class_index: int, num_presentations: int) -> str:
    candidate = PROFESSOR_AVAIL_CYCLE[class_index % len(PROFESSOR_AVAIL_CYCLE)]
    if num_presentations >= PROF_FULL_DAY_THRESHOLD and candidate in ("day1", "day2", "day3"):
        return "full"
    return candidate


def name_for(role: str, idx: int) -> str:
    first = FIRST_NAMES[idx % len(FIRST_NAMES)]
    role_salt = {"student": 0, "professor": 1}[role]
    last = LAST_NAMES[(idx * 7 + role_salt * 5) % len(LAST_NAMES)]
    return f"{first} {last}"


# ---------------------------------------------------------------------------
# Build all rows
# ---------------------------------------------------------------------------

def build_rows() -> dict[str, list[dict]]:
    sym_id = det_id("symposium")

    symposium = {
        "id": sym_id,
        "created_at": CREATED_AT,
        "name": SYMPOSIUM_NAME,
        "rooms_available": ROOMS_AVAILABLE,
        "default_buffer": DEFAULT_BUFFER,
    }

    sym_timeframes = [
        {
            "id": det_id("sym_tf", i),
            "linked_id": sym_id,
            "start_time": s.isoformat(),
            "end_time": e.isoformat(),
        }
        for i, (s, e) in enumerate(DAY_BOUNDS)
    ]

    departments: list[dict] = []
    classes: list[dict] = []
    professors: list[dict] = []
    prof_timeframes: list[dict] = []
    presentations: list[dict] = []
    students: list[dict] = []
    presenting_students: list[dict] = []
    student_timeframes: list[dict] = []

    prof_shape_counts: dict[str, int] = {}
    pres_shape_counts: dict[str, int] = {}

    global_pres_idx = 0
    global_student_idx = 0
    global_prof_idx = 0
    global_class_idx = 0

    for d_idx, (dept_name, head_name, class_list) in enumerate(DEPARTMENTS):
        dept_id = det_id("department", d_idx)
        departments.append({
            "id": dept_id,
            "department_name": dept_name,
            "department_head_name": head_name,
            "email": f"dept.{d_idx}@hamilton.edu",
            "symposium_id": sym_id,
        })

        for c_idx_in_dept, (class_name, num_presentations) in enumerate(class_list):
            class_id = det_id("class", d_idx, c_idx_in_dept)
            classes.append({
                "id": class_id,
                "name": class_name,
                "department_id": dept_id,
            })

            # Professor for this class.
            prof_id = det_id("professor", global_prof_idx)
            shape_name = professor_shape_name(global_class_idx, num_presentations)
            prof_avail = PROFESSOR_SHAPES[shape_name]()
            prof_shape_counts[shape_name] = prof_shape_counts.get(shape_name, 0) + 1

            professors.append({
                "id": prof_id,
                "name": name_for("professor", global_prof_idx),
                "email": f"prof.{global_prof_idx}@hamilton.edu",
                "class_id": class_id,
            })
            for tf_i, (s, e) in enumerate(prof_avail):
                prof_timeframes.append({
                    "id": det_id("prof_tf", global_prof_idx, tf_i),
                    "linked_id": prof_id,
                    "start_time": s.isoformat(),
                    "end_time": e.isoformat(),
                })
            global_prof_idx += 1

            # Presentations in this class.
            for p_idx_in_class in range(num_presentations):
                pres_id = det_id("presentation", d_idx, c_idx_in_dept, p_idx_in_class)
                duration = DURATION_CYCLE[global_pres_idx % len(DURATION_CYCLE)]
                group_size = GROUP_SIZE_CYCLE[global_pres_idx % len(GROUP_SIZE_CYCLE)]
                pres_shape = PRESENTATION_AVAIL_CYCLE[global_pres_idx % len(PRESENTATION_AVAIL_CYCLE)]
                pres_avail = PRESENTATION_SHAPES[pres_shape]()
                pres_shape_counts[pres_shape] = pres_shape_counts.get(pres_shape, 0) + 1

                title_suffix = (
                    "Solo Presentation" if group_size == 1
                    else f"Group of {group_size}"
                )
                presentations.append({
                    "id": pres_id,
                    "title": f"{class_name} — {title_suffix} #{p_idx_in_class + 1}",
                    "class_id": class_id,
                    "minutes": duration,
                    "buffer": DEFAULT_BUFFER,
                })

                # All members of a group share this presentation's windows
                # so the group's joint availability is never empty.
                for _ in range(group_size):
                    student_id = det_id("student", global_student_idx)
                    students.append({
                        "id": student_id,
                        "name": name_for("student", global_student_idx),
                        "email": f"student.{global_student_idx}@hamilton.edu",
                        "class_id": class_id,
                        "presentation_id": pres_id,
                    })
                    presenting_students.append({
                        "id": det_id("ps", global_student_idx),
                        "presentation_id": pres_id,
                        "student_id": student_id,
                    })
                    for tf_i, (s, e) in enumerate(pres_avail):
                        student_timeframes.append({
                            "id": det_id("stu_tf", global_student_idx, tf_i),
                            "linked_id": student_id,
                            "start_time": s.isoformat(),
                            "end_time": e.isoformat(),
                        })
                    global_student_idx += 1

                global_pres_idx += 1
            global_class_idx += 1

    return {
        "symposium": [symposium],
        "sym_timeframes": sym_timeframes,
        "departments": departments,
        "classes": classes,
        "professors": professors,
        "prof_timeframes": prof_timeframes,
        "presentations": presentations,
        "students": students,
        "student_timeframes": student_timeframes,
        "presenting_students": presenting_students,
        "_prof_shape_counts": prof_shape_counts,
        "_pres_shape_counts": pres_shape_counts,
    }


# ---------------------------------------------------------------------------
# DB I/O
# ---------------------------------------------------------------------------

def batch_insert(table: str, rows: list[dict], batch_size: int = 200) -> None:
    if not rows:
        return
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        supabase.table(table).insert(chunk).execute()
        total += len(chunk)
    print(f"  Inserted {total:>4} rows into {table}")


def wipe_previous_demo() -> None:
    """Delete the previously seeded varied demo so re-runs are idempotent."""
    sym_id = uuid.UUID(det_id("symposium"))
    counts = delete_symposium(sym_id)
    nonzero = {k: v for k, v in counts.items() if v}
    if nonzero:
        print(f"Cleared previous varied-availability demo symposium: {nonzero}")
    else:
        print("No previous varied-availability demo symposium found.")


def seed(rows: dict) -> None:
    print(f"\nSeeding '{SYMPOSIUM_NAME}'...")
    batch_insert("symposiums", rows["symposium"])
    batch_insert("timeframes", rows["sym_timeframes"])
    batch_insert("departments", rows["departments"])
    batch_insert("classes", rows["classes"])
    batch_insert("professors", rows["professors"])
    batch_insert("timeframes", rows["prof_timeframes"])
    batch_insert("presentations", rows["presentations"])
    batch_insert("students", rows["students"])
    batch_insert("timeframes", rows["student_timeframes"])
    batch_insert("presenting_students", rows["presenting_students"])

    print("\nDone.")
    print(f"  Symposium ID:    {rows['symposium'][0]['id']}")
    print(f"  Departments:     {len(rows['departments'])}")
    print(f"  Classes:         {len(rows['classes'])}")
    print(f"  Professors:      {len(rows['professors'])}")
    print(f"  Presentations:   {len(rows['presentations'])}")
    print(f"  Students:        {len(rows['students'])}")
    print(f"  Rooms:           {ROOMS_AVAILABLE}")
    print(f"  Days:            {len(DAY_BOUNDS)}")
    print("  Professor availability shapes:")
    for name in sorted(rows["_prof_shape_counts"]):
        print(f"    {name:12s} {rows['_prof_shape_counts'][name]}")
    print("  Presentation availability shapes (group members share these):")
    for name in sorted(rows["_pres_shape_counts"]):
        print(f"    {name:12s} {rows['_pres_shape_counts'][name]}")


def main() -> None:
    wipe_previous_demo()
    rows = build_rows()
    seed(rows)


if __name__ == "__main__":
    main()
