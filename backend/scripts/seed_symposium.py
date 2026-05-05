"""
Seed script: inserts a symposium of the requested size alongside existing data.

Usage (from the backend directory):
    python scripts/seed_symposium.py --size small
    python scripts/seed_symposium.py --size medium
    python scripts/seed_symposium.py --size large
    python scripts/seed_symposium.py --size massive --clear

--clear first deletes all existing data (children before parents). Previously
only `scripts/seed_massive_symposium.py` did this; it's now available for any size.
"""

import argparse
import os
from pathlib import Path
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


@dataclass(frozen=True)
class Preset:
    name: str
    email_prefix: str
    seed: int
    day_bounds: list[tuple[datetime, datetime]]
    num_professors: int
    num_classes: int
    students_per_class: int
    num_departments: int
    rooms_available: int
    coverage_low: float
    coverage_high: float
    coverage_mode: float
    max_windows_per_day: int
    window_count_weights: list[int]
    duration_choices: list[int]


def _day(y: int, m: int, d: int, start_h: int, end_h: int) -> tuple[datetime, datetime]:
    return (
        datetime(y, m, d, start_h, 0, tzinfo=timezone.utc),
        datetime(y, m, d, end_h, 0, tzinfo=timezone.utc),
    )


PRESETS: dict[str, Preset] = {
    "small": Preset(
        name="Small Symposium",
        email_prefix="small-",
        seed=7,
        day_bounds=[_day(2024, 3, 15, 13, 18)],
        num_professors=3,
        num_classes=3,
        students_per_class=4,
        num_departments=1,
        rooms_available=2,
        coverage_low=0.60,
        coverage_high=1.00,
        coverage_mode=0.80,
        max_windows_per_day=2,
        window_count_weights=[60, 40],
        duration_choices=[15, 20],
    ),
    "medium": Preset(
        name="Medium Symposium",
        email_prefix="medium-",
        seed=13,
        day_bounds=[_day(2024, 2, 5, 13, 20), _day(2024, 2, 6, 13, 20)],
        num_professors=6,
        num_classes=8,
        students_per_class=6,
        num_departments=2,
        rooms_available=4,
        coverage_low=0.55,
        coverage_high=1.00,
        coverage_mode=0.75,
        max_windows_per_day=3,
        window_count_weights=[50, 35, 15],
        duration_choices=[15, 20, 25],
    ),
    "large": Preset(
        name="Large Symposium",
        email_prefix="large-",
        seed=99,
        day_bounds=[
            _day(2024, 4, 8, 13, 21),
            _day(2024, 4, 9, 13, 21),
            _day(2024, 4, 10, 13, 21),
        ],
        num_professors=10,
        num_classes=10,
        students_per_class=10,
        num_departments=3,
        rooms_available=6,
        coverage_low=0.50,
        coverage_high=1.00,
        coverage_mode=0.75,
        max_windows_per_day=3,
        window_count_weights=[50, 35, 15],
        duration_choices=[15, 20, 25],
    ),
    "massive": Preset(
        name="Massive Symposium",
        email_prefix="",
        seed=42,
        day_bounds=[
            _day(2024, 1, 1, 14, 23),
            _day(2024, 1, 2, 14, 23),
            _day(2024, 1, 3, 14, 23),
        ],
        num_professors=15,
        num_classes=20,
        students_per_class=10,
        num_departments=4,
        rooms_available=8,
        coverage_low=0.50,
        coverage_high=1.00,
        coverage_mode=0.75,
        max_windows_per_day=3,
        window_count_weights=[50, 35, 15],
        duration_choices=[15, 20, 25],
    ),
}


def ustr(u: object) -> str:
    return str(u)


def delete_all() -> None:
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


def generate_data(preset: Preset) -> dict:
    rng = random.Random(preset.seed)

    def random_availability(coverage: float) -> list[tuple[datetime, datetime]]:
        windows: list[tuple[datetime, datetime]] = []
        for day_start, day_end in preset.day_bounds:
            day_minutes = int((day_end - day_start).total_seconds() / 60)
            target = max(60, min(day_minutes, round(day_minutes * coverage)))
            max_wins = min(preset.max_windows_per_day, target // 60)
            num_windows = rng.choices(
                range(1, max_wins + 1),
                weights=preset.window_count_weights[:max_wins],
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
            windows.append((preset.day_bounds[0][0], preset.day_bounds[0][1]))
        return windows

    def person_coverage() -> float:
        return rng.triangular(preset.coverage_low, preset.coverage_high, preset.coverage_mode)

    # --- Symposium ---
    symposium_id = uuid.uuid4()
    symposium = {
        "id": ustr(symposium_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": preset.name,
        "rooms_available": preset.rooms_available,
        "default_buffer": 5,
    }

    sym_timeframes = [
        {
            "id": ustr(uuid.uuid4()),
            "linked_id": ustr(symposium_id),
            "start_time": s.isoformat(),
            "end_time": e.isoformat(),
        }
        for s, e in preset.day_bounds
    ]

    # --- Departments ---
    departments = [
        {
            "id": ustr(uuid.uuid4()),
            "department_name": f"Department {d}",
            "department_head_name": f"Head {d}",
            "email": f"{preset.email_prefix}dept{d}@university.edu",
            "symposium_id": ustr(symposium_id),
        }
        for d in range(preset.num_departments)
    ]

    # --- Classes & professors ---
    prof_availability: dict[int, list[tuple[datetime, datetime]]] = {
        i: random_availability(person_coverage()) for i in range(preset.num_professors)
    }

    classes: list[dict] = []
    prof_records: list[dict] = []
    prof_id_by_index: dict[int, str] = {}

    for c in range(preset.num_classes):
        class_id = ustr(uuid.uuid4())
        dept_id = departments[c % preset.num_departments]["id"]
        classes.append({"id": class_id, "name": f"Class {c}", "department_id": dept_id})

        prof_index = c % preset.num_professors
        if prof_index not in prof_id_by_index:
            prof_uuid = ustr(uuid.uuid4())
            prof_id_by_index[prof_index] = prof_uuid
            prof_records.append({
                "id": prof_uuid,
                "name": f"Professor {prof_index}",
                "email": f"{preset.email_prefix}prof{prof_index}@university.edu",
                "class_id": class_id,
                "_availability": prof_availability[prof_index],
            })

    prof_timeframes = [
        {
            "id": ustr(uuid.uuid4()),
            "linked_id": pr["id"],
            "start_time": s.isoformat(),
            "end_time": e.isoformat(),
        }
        for pr in prof_records
        for s, e in pr["_availability"]
    ]

    professors_to_insert = [
        {k: v for k, v in pr.items() if not k.startswith("_")}
        for pr in prof_records
    ]

    # --- Students, presentations ---
    presentations: list[dict] = []
    students: list[dict] = []
    presenting_students: list[dict] = []
    student_timeframes: list[dict] = []

    title_prefix = preset.name.split()[0]  # "Small", "Medium", "Large", "Massive"
    student_name_prefix = title_prefix
    student_email_prefix = preset.email_prefix or ""

    for c in range(preset.num_classes):
        class_id = classes[c]["id"]
        for s in range(preset.students_per_class):
            avail = random_availability(person_coverage())
            duration = rng.choice(preset.duration_choices)

            pres_id = ustr(uuid.uuid4())
            student_id = ustr(uuid.uuid4())

            presentations.append({
                "id": pres_id,
                "title": f"{title_prefix} Class {c} — Student {s}"
                if preset.email_prefix else f"Class {c} — Student {s}",
                "class_id": class_id,
                "minutes": duration,
                "buffer": 5,
            })
            student_global_idx = c * preset.students_per_class + s
            students.append({
                "id": student_id,
                "name": (f"{student_name_prefix} Student {student_global_idx}"
                         if preset.email_prefix else f"Student {student_global_idx}"),
                "email": f"{student_email_prefix}student{student_global_idx}@university.edu",
                "class_id": class_id,
                "presentation_id": pres_id,
            })
            presenting_students.append({
                "id": ustr(uuid.uuid4()),
                "presentation_id": pres_id,
                "student_id": student_id,
            })
            for ws, we in avail:
                student_timeframes.append({
                    "id": ustr(uuid.uuid4()),
                    "linked_id": student_id,
                    "start_time": ws.isoformat(),
                    "end_time": we.isoformat(),
                })

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


def batch_insert(table: str, rows: list[dict], batch_size: int = 200) -> None:
    if not rows:
        return
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        supabase.table(table).insert(chunk).execute()
        total += len(chunk)
    print(f"  Inserted {total} rows into {table}")


def seed(data: dict, label: str) -> None:
    print(f"Seeding {label} symposium data...")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the DB with a sized symposium.")
    parser.add_argument(
        "--size",
        choices=sorted(PRESETS.keys()),
        required=True,
        help="Symposium size preset to seed.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing data before seeding.",
    )
    args = parser.parse_args()

    if args.clear:
        delete_all()

    preset = PRESETS[args.size]
    data = generate_data(preset)
    seed(data, args.size)


if __name__ == "__main__":
    main()
