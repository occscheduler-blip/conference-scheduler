"""
Seed script: inserts a small "Debugger Test" symposium engineered to produce
rich scheduler diagnostics and suggestions.

Three failure scenarios are baked in:

  Scenario A — Professor Bottleneck (Class "Bottleneck 101"):
    Professor "Dr. Narrow" is available 09:00–09:15 UTC (15 min).
    Three 20-minute presentations belong to her class.
    Because her window is shorter than any presentation, all three are
    pre-filtered with "no valid start times after availability filtering".

  Scenario B — Same-Class-Same-Room Crunch (Class "Crunch 202"):
    Professor "Dr. Full" is available the entire 2-hour window.
    Five 25-minute presentations must share one room (same_class_same_room=hard).
    Required room time: 5 × (25 + 5 buffer) = 150 min > 120 min available.
    At least one presentation cannot be scheduled.

  Scenario C — Student–Professor Time Gap (Class "Conflict 303"):
    Professor "Dr. Morning" is available 09:00–10:00 UTC.
    Two presentations each have one student available only 10:30–11:00 UTC.
    The professor and student windows never overlap → both presentations are
    pre-filtered with "no valid start times after availability filtering".

Expected diagnostics (5 × "no valid start times" + CP-SAT partial failure):
  - Presentation <id> has no valid start times after availability filtering. (×5)

Expected suggestions from _build_admin_suggestions:
  - Review professor availability windows for the blocked presentations.
  - Change same-class-same-room from hard to soft.
  - Reduce required room buffer or make that rule softer.

Usage (from the backend directory):
    python seed_debug_symposium.py
    python seed_debug_symposium.py --clear
"""

import argparse
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# All times are UTC.  The symposium runs 09:00–11:00 on 2026-05-20 (120 min).
DAY = "2026-05-20"
SYM_START = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
SYM_END = datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc)

# Professor windows
NARROW_START = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
NARROW_END = datetime(2026, 5, 20, 9, 15, tzinfo=timezone.utc)   # 15 min — shorter than any 20-min presentation

FULL_START = SYM_START
FULL_END = SYM_END

MORNING_START = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
MORNING_END = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)  # 09:00–10:00

# Students in Scenario C are only free *after* Dr. Morning leaves
LATE_STUDENT_START = datetime(2026, 5, 20, 10, 30, tzinfo=timezone.utc)
LATE_STUDENT_END = datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc)


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


def batch_insert(table: str, rows: list[dict]) -> None:
    if not rows:
        return
    supabase.table(table).insert(rows).execute()
    print(f"  Inserted {len(rows)} row(s) into {table}")


def generate() -> dict:
    # ── Symposium ──────────────────────────────────────────────────────────────
    sym_id = uid()
    symposium = {
        "id": sym_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": "Debugger Test Symposium",
        "rooms_available": 2,
        "default_buffer": 5,
    }
    sym_timeframes = [tf(sym_id, SYM_START, SYM_END)]

    # ── Department ─────────────────────────────────────────────────────────────
    dept_id = uid()
    department = {
        "id": dept_id,
        "department_name": "Department of Impossible Scheduling",
        "department_head_name": "Head Tester",
        "email": "debug-dept@university.edu",
        "symposium_id": sym_id,
    }

    # ── Scenario A: Professor Bottleneck ───────────────────────────────────────
    # Dr. Narrow's 15-min window < 20-min presentation → all 3 pre-filtered.
    class_a_id = uid()
    class_a = {"id": class_a_id, "name": "Bottleneck 101", "department_id": dept_id}

    prof_narrow_id = uid()
    prof_narrow = {
        "id": prof_narrow_id,
        "name": "Dr. Narrow",
        "email": "debug-narrow@university.edu",
        "class_id": class_a_id,
    }
    prof_narrow_tf = tf(prof_narrow_id, NARROW_START, NARROW_END)

    pres_a: list[dict] = []
    students_a: list[dict] = []
    presenting_students_a: list[dict] = []
    student_tfs_a: list[dict] = []
    for i in range(3):
        p_id = uid()
        s_id = uid()
        pres_a.append({
            "id": p_id,
            "title": f"Bottleneck Presentation {i + 1} (will be pre-filtered)",
            "class_id": class_a_id,
            "minutes": 20,
            "buffer": 5,
        })
        students_a.append({
            "id": s_id,
            "name": f"Student A{i + 1}",
            "email": f"debug-student-a{i + 1}@university.edu",
            "class_id": class_a_id,
            "presentation_id": p_id,
        })
        presenting_students_a.append({"id": uid(), "presentation_id": p_id, "student_id": s_id})
        # Students fully available — the professor window is the only blocker.
        student_tfs_a.append(tf(s_id, SYM_START, SYM_END))

    # ── Scenario B: Same-Class-Same-Room Crunch ────────────────────────────────
    # 5 × (25 min presentation + 5 min buffer) = 150 min > 120 min per room.
    class_b_id = uid()
    class_b = {"id": class_b_id, "name": "Crunch 202", "department_id": dept_id}

    prof_full_id = uid()
    prof_full = {
        "id": prof_full_id,
        "name": "Dr. Full",
        "email": "debug-full@university.edu",
        "class_id": class_b_id,
    }
    prof_full_tf = tf(prof_full_id, FULL_START, FULL_END)

    pres_b: list[dict] = []
    students_b: list[dict] = []
    presenting_students_b: list[dict] = []
    student_tfs_b: list[dict] = []
    for i in range(5):
        p_id = uid()
        s_id = uid()
        pres_b.append({
            "id": p_id,
            "title": f"Crunch Presentation {i + 1} (at least 1 will be unscheduled)",
            "class_id": class_b_id,
            "minutes": 25,
            "buffer": 5,
        })
        students_b.append({
            "id": s_id,
            "name": f"Student B{i + 1}",
            "email": f"debug-student-b{i + 1}@university.edu",
            "class_id": class_b_id,
            "presentation_id": p_id,
        })
        presenting_students_b.append({"id": uid(), "presentation_id": p_id, "student_id": s_id})
        student_tfs_b.append(tf(s_id, SYM_START, SYM_END))

    # ── Scenario C: Student–Professor Time Gap ─────────────────────────────────
    # Professor available 09:00–10:00, students available 10:30–11:00 → no overlap.
    class_c_id = uid()
    class_c = {"id": class_c_id, "name": "Conflict 303", "department_id": dept_id}

    prof_morning_id = uid()
    prof_morning = {
        "id": prof_morning_id,
        "name": "Dr. Morning",
        "email": "debug-morning@university.edu",
        "class_id": class_c_id,
    }
    prof_morning_tf = tf(prof_morning_id, MORNING_START, MORNING_END)

    pres_c: list[dict] = []
    students_c: list[dict] = []
    presenting_students_c: list[dict] = []
    student_tfs_c: list[dict] = []
    for i in range(2):
        p_id = uid()
        s_id = uid()
        pres_c.append({
            "id": p_id,
            "title": f"Gap Presentation {i + 1} (will be pre-filtered — student/prof never overlap)",
            "class_id": class_c_id,
            "minutes": 20,
            "buffer": 5,
        })
        students_c.append({
            "id": s_id,
            "name": f"Student C{i + 1}",
            "email": f"debug-student-c{i + 1}@university.edu",
            "class_id": class_c_id,
            "presentation_id": p_id,
        })
        presenting_students_c.append({"id": uid(), "presentation_id": p_id, "student_id": s_id})
        # Students only free after Dr. Morning's window ends.
        student_tfs_c.append(tf(s_id, LATE_STUDENT_START, LATE_STUDENT_END))

    return {
        "symposium": symposium,
        "sym_timeframes": sym_timeframes,
        "departments": [department],
        "classes": [class_a, class_b, class_c],
        "professors": [prof_narrow, prof_full, prof_morning],
        "prof_timeframes": [prof_narrow_tf, prof_full_tf, prof_morning_tf],
        "presentations": pres_a + pres_b + pres_c,
        "students": students_a + students_b + students_c,
        "presenting_students": presenting_students_a + presenting_students_b + presenting_students_c,
        "student_timeframes": student_tfs_a + student_tfs_b + student_tfs_c,
    }


def seed(data: dict) -> None:
    print("Seeding Debugger Test Symposium...\n")

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
    print(f"""
Done. Symposium ID: {sym["id"]}

What to expect when you run the scheduler on this symposium
-----------------------------------------------------------
Scenario A — Professor Bottleneck (Bottleneck 101):
  Dr. Narrow is available 09:00–09:15 UTC (15 min).
  All 3 presentations are 20 min, so her window is too short.
  → 3× diagnostic: "Presentation <id> has no valid start times after availability filtering."

Scenario B — Same-Class-Same-Room Crunch (Crunch 202):
  5 presentations × 30 min (25 + 5 buffer) = 150 min must fit in 1 room (120 min).
  → At least 1 presentation unscheduled by CP-SAT.

Scenario C — Student–Professor Gap (Conflict 303):
  Dr. Morning leaves at 10:00; students only arrive at 10:30.
  → 2× diagnostic: "Presentation <id> has no valid start times after availability filtering."

Expected suggestions:
  • Review professor availability windows for the blocked presentations.
  • Change same-class-same-room from hard to soft.
  • Reduce required room buffer or make that rule softer.

All defaults (professor_availability=hard, student_availability=hard,
same_class_same_room=hard) must be left unchanged for the failures to appear.
""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the DB with a debugger-test symposium.")
    parser.add_argument("--clear", action="store_true", help="Delete all existing data first.")
    args = parser.parse_args()

    if args.clear:
        delete_all()

    data = generate()
    seed(data)


if __name__ == "__main__":
    main()
