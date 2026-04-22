"""
Seed script: clears all data from the DB and inserts the massive symposium test data.
Run from the backend directory: python seed_massive_symposium.py
"""

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ustr(u) -> str:
    return str(u)


def delete_all():
    """Delete all rows in dependency order (children before parents)."""
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
    print("All existing data deleted.\n")


# ---------------------------------------------------------------------------
# Generate test data (same logic as test_massive_symposium, seed=42)
# ---------------------------------------------------------------------------

def generate_data():
    rng = random.Random(42)

    day_bounds = [
        (datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc), datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)),
        (datetime(2024, 1, 2, 14, 0, tzinfo=timezone.utc), datetime(2024, 1, 2, 23, 0, tzinfo=timezone.utc)),
        (datetime(2024, 1, 3, 14, 0, tzinfo=timezone.utc), datetime(2024, 1, 3, 23, 0, tzinfo=timezone.utc)),
    ]

    def random_availability(coverage: float) -> list:
        """Generate windows covering ~coverage fraction of each symposium day.

        coverage is a per-person fraction (e.g. 0.75 = available 75% of each day).
        Windows vary in number (1–3 per day) and placement to give realistic variety.
        """
        windows = []
        for day_start, day_end in day_bounds:
            day_minutes = int((day_end - day_start).total_seconds() / 60)  # 600
            target = max(60, min(day_minutes, round(day_minutes * coverage)))

            # Pick 1–3 windows; cap so each window can be at least 60 min
            max_wins = min(3, target // 60)
            num_windows = rng.choices(
                range(1, max_wins + 1),
                weights=[50, 35, 15][: max_wins],
            )[0]

            placed: list[tuple[int, int]] = []
            remaining = target
            for w in range(num_windows):
                wins_left = num_windows - w
                min_len = 60
                max_len = remaining - min_len * (wins_left - 1)
                if max_len < min_len:
                    break
                win_len = rng.randint(min_len, max_len)
                for _attempt in range(20):
                    s = rng.randint(0, day_minutes - win_len)
                    e = s + win_len
                    if all(e <= ws or s >= we for ws, we in placed):
                        placed.append((s, e))
                        windows.append((
                            day_start + timedelta(minutes=s),
                            day_start + timedelta(minutes=e),
                        ))
                        remaining -= win_len
                        break

        if not windows:
            windows.append((day_bounds[0][0], day_bounds[0][1]))
        return windows

    def person_coverage() -> float:
        """Sample a per-person availability fraction, mean ~0.75, range ~0.50–1.00."""
        return rng.triangular(0.50, 1.00, 0.75)

    NUM_PROFESSORS = 15
    NUM_CLASSES = 20
    STUDENTS_PER_CLASS = 10
    NUM_DEPARTMENTS = 4  # group 20 classes into 4 departments (5 classes each)

    # --- Symposium ---
    symposium_id = uuid.uuid4()
    symposium = {
        "id": ustr(symposium_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": "Massive Symposium",
        "rooms_available": 8,
        "default_buffer": 5,
    }

    # Symposium timeframes
    sym_timeframes = [
        {
            "id": ustr(uuid.uuid4()),
            "linked_id": ustr(symposium_id),
            "start_time": s.isoformat(),
            "end_time": e.isoformat(),
        }
        for s, e in day_bounds
    ]

    # --- Departments ---
    departments = []
    for d in range(NUM_DEPARTMENTS):
        departments.append({
            "id": ustr(uuid.uuid4()),
            "department_name": f"Department {d}",
            "department_head_name": f"Head {d}",
            "email": f"dept{d}@university.edu",
            "symposium_id": ustr(symposium_id),
        })

    # --- Classes & their professors ---
    # Professor availability (keyed by index)
    prof_availability: dict[int, list] = {}
    for i in range(NUM_PROFESSORS):
        prof_availability[i] = random_availability(person_coverage())

    classes = []
    prof_records = []  # {id, name, email, class_id, availability_windows}
    prof_id_by_index: dict[int, str] = {}

    for c in range(NUM_CLASSES):
        class_id = ustr(uuid.uuid4())
        dept_id = departments[c % NUM_DEPARTMENTS]["id"]
        classes.append({
            "id": class_id,
            "name": f"Class {c}",
            "department_id": dept_id,
        })

        prof_index = c % NUM_PROFESSORS
        if prof_index not in prof_id_by_index:
            prof_uuid = ustr(uuid.uuid4())
            prof_id_by_index[prof_index] = prof_uuid
            prof_records.append({
                "id": prof_uuid,
                "name": f"Professor {prof_index}",
                "email": f"prof{prof_index}@university.edu",
                "class_id": class_id,
                "_availability": prof_availability[prof_index],
            })
        else:
            # Professor teaches multiple classes — update class_id link to first class
            # (schema only has one class_id per professor; keep the first assignment)
            pass

    # --- Professor timeframes ---
    prof_timeframes = []
    for pr in prof_records:
        for s, e in pr["_availability"]:
            prof_timeframes.append({
                "id": ustr(uuid.uuid4()),
                "linked_id": pr["id"],
                "start_time": s.isoformat(),
                "end_time": e.isoformat(),
            })

    # Strip internal _availability key before inserting
    professors_to_insert = [
        {k: v for k, v in pr.items() if not k.startswith("_")}
        for pr in prof_records
    ]

    # --- Students, presentations, student timeframes ---
    presentations = []
    students = []
    presenting_students = []
    student_timeframes = []

    pres_idx = 0
    for c in range(NUM_CLASSES):
        class_id = classes[c]["id"]
        for s in range(STUDENTS_PER_CLASS):
            student_availability = random_availability(person_coverage())
            duration = rng.choice([15, 20, 25])

            pres_id = ustr(uuid.uuid4())
            student_id = ustr(uuid.uuid4())

            presentations.append({
                "id": pres_id,
                "title": f"Class {c} — Student {s}",
                "class_id": class_id,
                "minutes": duration,
                "buffer": 5,
            })

            students.append({
                "id": student_id,
                "name": f"Student {c * STUDENTS_PER_CLASS + s}",
                "email": f"student{c * STUDENTS_PER_CLASS + s}@university.edu",
                "class_id": class_id,
                "presentation_id": pres_id,
            })

            presenting_students.append({
                "id": ustr(uuid.uuid4()),
                "presentation_id": pres_id,
                "student_id": student_id,
            })

            for ws, we in student_availability:
                student_timeframes.append({
                    "id": ustr(uuid.uuid4()),
                    "linked_id": student_id,
                    "start_time": ws.isoformat(),
                    "end_time": we.isoformat(),
                })

            pres_idx += 1

    return {
        "symposium": symposium,
        "sym_timeframes": sym_timeframes,
        "departments": departments,
        "classes": classes,
        "professors": professors_to_insert,
        "prof_timeframes": prof_timeframes,
        "presentations": presentations,
        "students": students,
        "presenting_students": presenting_students,
        "student_timeframes": student_timeframes,
    }


def batch_insert(table: str, rows: list[dict], batch_size: int = 200):
    if not rows:
        return
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        supabase.table(table).insert(chunk).execute()
        total += len(chunk)
    print(f"  Inserted {total} rows into {table}")


def seed(data: dict):
    print("Seeding massive symposium data...")
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
    print("Done seeding.\n")
    print(f"  Symposium ID: {data['symposium']['id']}")
    print(f"  Departments:  {len(data['departments'])}")
    print(f"  Classes:      {len(data['classes'])}")
    print(f"  Professors:   {len(data['professors'])}")
    print(f"  Presentations:{len(data['presentations'])}")
    print(f"  Students:     {len(data['students'])}")


if __name__ == "__main__":
    delete_all()
    data = generate_data()
    seed(data)
