"""
Seed script: a large symposium engineered to fail under default constraints
in a way the debugger can fix by relaxing professor_availability.

Why "large": 17 classes × 6 presentations = 102 presentations.  Both the
presentation-count threshold (>100) and the class-count threshold (>15) in
service._should_use_hierarchical fire, so build_schedule_for_symposium routes
to solve_hierarchical.

Why it fails under defaults: 5 of the 17 professors have a 60-minute
availability window.  Their class needs 6 × (20 + 5) = 150 min of
contiguous-or-fragmented room time.  With the default
same_class_same_room=hard, all six presentations of each class must share one
room; with professor_availability=hard, they can only happen inside the
prof's 60-min window.  Only 2 presentations (60 / 30) fit per narrow class →
4 presentations × 5 narrow classes = 20 unscheduled.

What the debugger should find: softening professor_availability lets phase 1
treat the narrow prof windows as soft, expanding allowed_windows to the full
symposium day; the remaining 20 presentations now place. The "Debugger
findings" modal should surface "[Debugger] Set professor availability to
Soft." and offer a 102/102 schedule via Accept & Apply.

The other 12 classes have wide-open prof windows so they schedule cleanly in
the initial run — this isolates the failure to one knob.

Usage (from the backend directory):
    python scripts/seed_large_failing_symposium.py
    python scripts/seed_large_failing_symposium.py --clear
"""

import argparse
import os
from pathlib import Path
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Single-day symposium, 09:00–17:00 UTC = 480 min.
SYM_START = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
SYM_END = datetime(2026, 5, 20, 17, 0, tzinfo=timezone.utc)

# Narrow professors get a 60-min window centered mid-day. 60 min < 150 min
# class total, and with same_class_same_room=hard the class can't split, so
# 4 of the 6 presentations get refused.
NARROW_START = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
NARROW_END = datetime(2026, 5, 20, 13, 0, tzinfo=timezone.utc)

NUM_CLASSES = 17
PRESENTATIONS_PER_CLASS = 6
PRESENTATION_MINUTES = 20
PRESENTATION_BUFFER = 5
NARROW_CLASS_INDICES = {0, 3, 6, 9, 12}  # 5 of 17 — the failure surface
ROOMS_AVAILABLE = 8


def uid() -> str:
    return str(uuid.uuid4())


def tf(linked_id: str, start: datetime, end: datetime) -> dict:
    return {
        "id": uid(),
        "linked_id": linked_id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    }


def delete_all() -> None:
    print("Deleting all existing data...")
    tables = [
        "presenting_students",
        "requests",
        "timeframes",
        "temporary_timeframes",
        "students",
        "presentations",
        "professors",
        "classes",
        "departments",
        "symposiums",
    ]
    for table in tables:
        resp = supabase.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        count = len(resp.data) if resp.data else 0
        print(f"  Deleted {count} rows from {table}")
    print("Done.\n")


def batch_insert(table: str, rows: list[dict], batch_size: int = 200) -> None:
    if not rows:
        return
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        supabase.table(table).insert(chunk).execute()
        total += len(chunk)
    print(f"  Inserted {total} row(s) into {table}")


def generate() -> dict:
    sym_id = uid()
    symposium = {
        "id": sym_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": "Large Failing Symposium (Debugger Test)",
        "rooms_available": ROOMS_AVAILABLE,
        "default_buffer": PRESENTATION_BUFFER,
    }
    sym_timeframes = [tf(sym_id, SYM_START, SYM_END)]

    dept_id = uid()
    departments = [
        {
            "id": dept_id,
            "department_name": "Department of Stress-Test Scheduling",
            "department_head_name": "Head Stress-Tester",
            "email": "large-failing-dept@university.edu",
            "symposium_id": sym_id,
        }
    ]

    classes: list[dict] = []
    professors: list[dict] = []
    prof_timeframes: list[dict] = []
    presentations: list[dict] = []
    students: list[dict] = []
    presenting_students: list[dict] = []
    student_timeframes: list[dict] = []

    for c in range(NUM_CLASSES):
        class_id = uid()
        classes.append({"id": class_id, "name": f"Stress Class {c:02d}", "department_id": dept_id})

        prof_id = uid()
        is_narrow = c in NARROW_CLASS_INDICES
        professors.append({
            "id": prof_id,
            "name": f"{'Dr. Narrow' if is_narrow else 'Dr. Open'} {c:02d}",
            "email": f"large-failing-prof-{c:02d}@university.edu",
            "class_id": class_id,
        })
        if is_narrow:
            prof_timeframes.append(tf(prof_id, NARROW_START, NARROW_END))
        else:
            prof_timeframes.append(tf(prof_id, SYM_START, SYM_END))

        for s in range(PRESENTATIONS_PER_CLASS):
            pres_id = uid()
            student_id = uid()
            label = f"C{c:02d}-P{s}"
            presentations.append({
                "id": pres_id,
                "title": f"{'(narrow) ' if is_narrow else ''}{label}",
                "class_id": class_id,
                "minutes": PRESENTATION_MINUTES,
                "buffer": PRESENTATION_BUFFER,
            })
            students.append({
                "id": student_id,
                "name": f"Student {label}",
                "email": f"large-failing-student-{c:02d}-{s}@university.edu",
                "class_id": class_id,
                "presentation_id": pres_id,
            })
            presenting_students.append({"id": uid(), "presentation_id": pres_id, "student_id": student_id})
            # All students fully available so their windows aren't the bottleneck.
            student_timeframes.append(tf(student_id, SYM_START, SYM_END))

    return {
        "symposium": symposium,
        "sym_timeframes": sym_timeframes,
        "departments": departments,
        "classes": classes,
        "professors": professors,
        "prof_timeframes": prof_timeframes,
        "presentations": presentations,
        "students": students,
        "presenting_students": presenting_students,
        "student_timeframes": student_timeframes,
    }


def seed(data: dict) -> None:
    print("Seeding Large Failing Symposium...\n")

    batch_insert("symposiums", [data["symposium"]])
    batch_insert("timeframes", data["sym_timeframes"])
    batch_insert("departments", data["departments"])
    batch_insert("classes", data["classes"])
    batch_insert("professors", data["professors"])
    batch_insert("timeframes", data["prof_timeframes"])
    batch_insert("presentations", data["presentations"])
    batch_insert("students", data["students"])
    batch_insert("timeframes", data["student_timeframes"])
    batch_insert("presenting_students", data["presenting_students"])

    sym = data["symposium"]
    n_pres = len(data["presentations"])
    n_classes = len(data["classes"])
    n_narrow = len(NARROW_CLASS_INDICES)
    print(f"""
Done. Symposium ID: {sym["id"]}

Shape
-----
  {n_classes} classes × {PRESENTATIONS_PER_CLASS} presentations each = {n_pres} presentations
  {n_narrow} narrow professors (60-min window 12:00–13:00 UTC)
  {n_classes - n_narrow} open professors (full day 09:00–17:00 UTC)
  {ROOMS_AVAILABLE} rooms, default_buffer={PRESENTATION_BUFFER} min, presentations={PRESENTATION_MINUTES} min

Why this triggers the hierarchical solver
-----------------------------------------
  presentations ({n_pres}) > 100  →  hierarchical
  classes       ({n_classes}) > 15   →  hierarchical (same dispatch path)

Expected initial run (defaults: prof_availability=hard, same_class_same_room=hard)
---------------------------------------------------------------------------------
  - Each narrow class needs 6 × (20 + 5) = 150 min in one room.
  - The narrow prof's 60-min window only fits 2 presentations.
  - same_class_same_room=hard forbids splitting across rooms.
  → ~{n_narrow * (PRESENTATIONS_PER_CLASS - 2)} presentations unscheduled across {n_narrow} narrow classes.
  → "Run Debugger" button appears in the Scheduler Failure popup.

Expected debugger output
------------------------
  - The 2^5 - 1 = 31 probes run with the hierarchical solver (~5–10 min wall time).
  - Best probe relaxes professor_availability → all {n_pres} schedule.
  - Modal hint: "[Debugger] Set professor availability to Soft."
  - Accept & Apply persists the full schedule into temporary_timeframes /
    presentations.temporary_room.

Notes
-----
  - student_availability defaults to soft already, so it is not a blocker here.
  - room_conflicts and person_conflicts stay hard with no impact (no double-bookings).
  - Run from the Admin → Schedule tab. Make sure no other scheduler job is
    pending for this symposium (the scheduler_jobs_singleton constraint will
    409 a duplicate kick-off).
""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a large failing symposium for testing the hierarchical debugger.")
    parser.add_argument("--clear", action="store_true", help="Delete all existing data first.")
    args = parser.parse_args()

    if args.clear:
        delete_all()

    data = generate()
    seed(data)


if __name__ == "__main__":
    main()
