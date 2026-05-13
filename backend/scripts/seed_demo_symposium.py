"""
Seed script: deterministic demo symposium for the conference scheduler.

This script always produces the *exact same* symposium — same UUIDs, same
departments, same classes, same presentations, same group sizes, same
durations, same availabilities — every time it is run. It exists so that
the live project demo is fully reproducible.

The data is intentionally large (~356 presentations, ~500 students) and
shaped to exercise the scheduler:

  - 10 departments of varying size (1 class to 8 classes)
  - 43 classes ranging from 4 to 16 presentations
  - Solo, pair, and trio presentations cycled deterministically
  - Presentation durations cycled deterministically across 10–30 min
  - 3-day symposium, 10 rooms, 5-min default buffer
  - Most people fully available, with a small deterministic minority of
    restricted availabilities for variety

Re-runs are idempotent: the previously seeded demo symposium is deleted
first (by its stable UUID) before fresh data is inserted.

Run from the backend directory:
    python scripts/seed_demo_symposium.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
# uuid5(namespace, name) returns the same UUID for the same inputs every
# time. Using a fixed namespace + descriptive name means every entity in
# this seed has a stable, predictable id.

DEMO_NS = uuid.UUID("d3c0d3c0-d3c0-d3c0-d3c0-d3c0d3c0d3c1")
# d3c0d3c0-d3c0-d3c0-d3c0-d3c0d3c0d3c0 for the unscheduled one
# d3c0d3c0-d3c0-d3c0-d3c0-d3c0d3c0d3c1 for the scheduled one

def det_id(*parts: object) -> str:
    return str(uuid.uuid5(DEMO_NS, ":".join(str(p) for p in parts)))


# ---------------------------------------------------------------------------
# Symposium configuration
# ---------------------------------------------------------------------------

SYMPOSIUM_NAME = "Hamilton Spring 2026 Demo Symposium - Scheduled"
ROOMS_AVAILABLE = 10
DEFAULT_BUFFER = 5

# 3 days, 9 AM – 5 PM UTC. Backend stores UTC; the frontend displays in
# Eastern time (Hamilton is the only audience).
DAY_BOUNDS: list[tuple[datetime, datetime]] = [
    (datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
     datetime(2026, 5, 11, 17, 0, tzinfo=timezone.utc)),
    (datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
     datetime(2026, 5, 12, 17, 0, tzinfo=timezone.utc)),
    (datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
     datetime(2026, 5, 13, 17, 0, tzinfo=timezone.utc)),
]

# Pinned creation time so the symposiums row is byte-identical between runs.
CREATED_AT = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()


# Departments. Each entry: (department_name, head_name, [(class_name, num_presentations), ...]).
# Sizes are intentionally varied so the demo shows large, medium, and tiny
# departments side by side.
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

# Group size cycle, indexed by global presentation index.
# Average 1.4 students per presentation. ~70% solo, ~20% pair, ~10% trio.
GROUP_SIZE_CYCLE = [1, 1, 1, 2, 1, 3, 1, 1, 2, 1]

# Duration cycle (minutes), indexed by global presentation index.
# Range 10–30, mean 20.
DURATION_CYCLE = [20, 15, 20, 25, 20, 10, 20, 30, 20, 20, 15, 25]

# Name pools cycled through deterministically.
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

# A deterministic minority of restricted availabilities, picked by index.
# Tuned to keep the schedule solvable while still showing the scheduler
# respects per-person windows.
STUDENT_MORNING_ONLY = 17   # every 17th student: each day 9am-12pm
STUDENT_DAY1_ONLY    = 23   # every 23rd student: only the first day
PROF_AFTERNOON_ONLY  = 11   # every 11th professor: each day 1pm-5pm


# ---------------------------------------------------------------------------
# Availability shapes
# ---------------------------------------------------------------------------

def full_availability() -> list[tuple[datetime, datetime]]:
    return list(DAY_BOUNDS)


def morning_only() -> list[tuple[datetime, datetime]]:
    return [(s, s + timedelta(hours=3)) for s, _ in DAY_BOUNDS]


def afternoon_only() -> list[tuple[datetime, datetime]]:
    return [(e - timedelta(hours=4), e) for _, e in DAY_BOUNDS]


def day1_only() -> list[tuple[datetime, datetime]]:
    return [DAY_BOUNDS[0]]


def name_for(role: str, idx: int) -> str:
    """Stable human-looking name from a (role, index) pair."""
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

    global_pres_idx = 0
    global_student_idx = 0
    global_prof_idx = 0

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

            # One professor per class.
            prof_id = det_id("professor", global_prof_idx)
            prof_avail = (
                afternoon_only()
                if global_prof_idx % PROF_AFTERNOON_ONLY == PROF_AFTERNOON_ONLY - 1
                else full_availability()
            )
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

                # Students for this presentation (1 to 3).
                for member_idx in range(group_size):
                    student_id = det_id("student", global_student_idx)

                    if global_student_idx % STUDENT_MORNING_ONLY == STUDENT_MORNING_ONLY - 1:
                        student_avail = morning_only()
                    elif global_student_idx % STUDENT_DAY1_ONLY == STUDENT_DAY1_ONLY - 1:
                        student_avail = day1_only()
                    else:
                        student_avail = full_availability()

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
                    for tf_i, (s, e) in enumerate(student_avail):
                        student_timeframes.append({
                            "id": det_id("stu_tf", global_student_idx, tf_i),
                            "linked_id": student_id,
                            "start_time": s.isoformat(),
                            "end_time": e.isoformat(),
                        })
                    global_student_idx += 1

                global_pres_idx += 1

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
    """Delete the previously seeded demo symposium so re-runs are idempotent."""
    sym_id = uuid.UUID(det_id("symposium"))
    counts = delete_symposium(sym_id)
    nonzero = {k: v for k, v in counts.items() if v}
    if nonzero:
        print(f"Cleared previous demo symposium: {nonzero}")
    else:
        print("No previous demo symposium found.")


def seed(rows: dict[str, list[dict]]) -> None:
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

    group_counts = {1: 0, 2: 0, 3: 0}
    for p in rows["presentations"]:
        members = sum(
            1 for ps in rows["presenting_students"]
            if ps["presentation_id"] == p["id"]
        )
        group_counts[members] = group_counts.get(members, 0) + 1

    print("\nDone.")
    print(f"  Symposium ID:    {rows['symposium'][0]['id']}")
    print(f"  Departments:     {len(rows['departments'])}")
    print(f"  Classes:         {len(rows['classes'])}")
    print(f"  Professors:      {len(rows['professors'])}")
    print(f"  Presentations:   {len(rows['presentations'])}")
    print(f"    Solo:          {group_counts.get(1, 0)}")
    print(f"    Pairs:         {group_counts.get(2, 0)}")
    print(f"    Trios:         {group_counts.get(3, 0)}")
    print(f"  Students:        {len(rows['students'])}")
    print(f"  Rooms:           {ROOMS_AVAILABLE}")
    print(f"  Days:            {len(DAY_BOUNDS)}")


def main() -> None:
    wipe_previous_demo()
    rows = build_rows()
    seed(rows)


if __name__ == "__main__":
    main()
