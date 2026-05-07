"""
Seed script: clears all data from the DB and inserts a symposium where:
  - departments vary in size (some have many classes, some few)
  - one department has a single class with 40 presentations
  - presentations are 10–30 minutes (most are 20)
  - students are mostly fully available; only ~5% have varied availabilities

Run from the backend directory: python scripts/seed_uniform_symposium.py
"""

import os
from pathlib import Path
import random
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ustr(u) -> str:
    return str(u)


# ---------------------------------------------------------------------------
# Generate test data
# ---------------------------------------------------------------------------

# Fraction of students who get a varied (restricted) availability.
# The rest are available for the entire symposium.
VARIED_FRACTION = 0.05


def generate_data():
    rng = random.Random(42)

    day_bounds = [
        (datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc), datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc)),
        (datetime(2024, 1, 2, 9, 0, tzinfo=timezone.utc), datetime(2024, 1, 2, 17, 0, tzinfo=timezone.utc)),
        (datetime(2024, 1, 3, 9, 0, tzinfo=timezone.utc), datetime(2024, 1, 3, 17, 0, tzinfo=timezone.utc)),
    ]

    def random_availability(coverage: float) -> list:
        """Generate windows covering ~coverage fraction of each symposium day."""
        windows = []
        for day_start, day_end in day_bounds:
            day_minutes = int((day_end - day_start).total_seconds() / 60)
            target = max(60, min(day_minutes, round(day_minutes * coverage)))

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

    def full_availability() -> list:
        """Return windows covering the entire symposium (every day fully)."""
        return [(s, e) for s, e in day_bounds]

    def person_coverage() -> float:
        return rng.triangular(0.50, 1.00, 0.75)

    def random_duration() -> int:
        """Presentation length, 10–30 min, mostly 20."""
        return rng.choices(
            [10, 15, 20, 25, 30],
            weights=[5, 15, 60, 15, 5],
        )[0]

    # --- Symposium ---
    symposium_id = uuid.uuid4()
    symposium = {
        "id": ustr(symposium_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": "Uniform Availability Symposium",
        "rooms_available": 8,
        "default_buffer": 5,
    }

    sym_timeframes = [
        {
            "id": ustr(uuid.uuid4()),
            "linked_id": ustr(symposium_id),
            "start_time": s.isoformat(),
            "end_time": e.isoformat(),
        }
        for s, e in day_bounds
    ]

    # --- Department / class layout ---
    # One special department: 1 class with 40 presentations.
    # Other departments: variable sizes (some big, some small).
    # Layout is (class_sizes_per_dept, dept_name_suffix_optional).
    dept_class_sizes: list[list[int]] = [
        [40],                  # special: 1 class, 40 presentations
        [12, 10, 9, 8, 8, 7],  # large department
        [11, 9, 8, 6],         # medium-large
        [7, 6, 5],             # medium
        [4, 3],                # small
        [2],                   # tiny: 1 class, 2 presentations
    ]

    NUM_DEPARTMENTS = len(dept_class_sizes)

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

    # --- Classes (variable per department) ---
    classes = []
    # Map from class_index -> (dept_index, num_students_in_class)
    class_meta: list[tuple[int, int]] = []
    for d, sizes in enumerate(dept_class_sizes):
        for size in sizes:
            class_id = ustr(uuid.uuid4())
            classes.append({
                "id": class_id,
                "name": f"Class {len(classes)}",
                "department_id": departments[d]["id"],
            })
            class_meta.append((d, size))

    NUM_CLASSES = len(classes)

    # --- Professors (one per class for simplicity) ---
    prof_records = []
    for c in range(NUM_CLASSES):
        prof_uuid = ustr(uuid.uuid4())
        prof_records.append({
            "id": prof_uuid,
            "name": f"Professor {c}",
            "email": f"prof{c}@university.edu",
            "class_id": classes[c]["id"],
            "_availability": random_availability(person_coverage()),
        })

    prof_timeframes = []
    for pr in prof_records:
        for s, e in pr["_availability"]:
            prof_timeframes.append({
                "id": ustr(uuid.uuid4()),
                "linked_id": pr["id"],
                "start_time": s.isoformat(),
                "end_time": e.isoformat(),
            })

    professors_to_insert = [
        {k: v for k, v in pr.items() if not k.startswith("_")}
        for pr in prof_records
    ]

    # --- Students, presentations, student timeframes ---
    total_students = sum(size for _, size in class_meta)
    num_varied = round(total_students * VARIED_FRACTION)
    varied_indices = set(rng.sample(range(total_students), num_varied))

    presentations = []
    students = []
    presenting_students = []
    student_timeframes = []

    student_idx = 0
    varied_count = 0
    for c, (_, size) in enumerate(class_meta):
        class_id = classes[c]["id"]
        for s in range(size):
            if student_idx in varied_indices:
                student_availability = random_availability(person_coverage())
                varied_count += 1
            else:
                student_availability = full_availability()

            duration = random_duration()

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
                "name": f"Student {student_idx}",
                "email": f"student{student_idx}@university.edu",
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

            student_idx += 1

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
        "_varied_count": varied_count,
        "_total_students": total_students,
        "_dept_class_sizes": dept_class_sizes,
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
    print("Seeding uniform-availability symposium data...")
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
    print(f"  Symposium ID:        {data['symposium']['id']}")
    print(f"  Departments:         {len(data['departments'])}")
    for d, sizes in enumerate(data['_dept_class_sizes']):
        print(f"    Dept {d}: {len(sizes)} classes, sizes={sizes}, total={sum(sizes)}")
    print(f"  Classes:             {len(data['classes'])}")
    print(f"  Professors:          {len(data['professors'])}")
    print(f"  Presentations:       {len(data['presentations'])}")
    print(f"  Students:            {len(data['students'])}")
    print(
        f"  Varied availability: {data['_varied_count']} / {data['_total_students']} "
        f"({data['_varied_count'] / data['_total_students']:.0%})"
    )


if __name__ == "__main__":
    data = generate_data()
    seed(data)
