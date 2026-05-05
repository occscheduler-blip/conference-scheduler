"""Seed a synthetic large symposium for end-to-end testing of the scheduler.

The hierarchical scheduler kicks in for ~100+ presentations or 15+ classes; this
script generates symposiums at the user's stated typical (300) and absolute
upper-bound (400) sizes.

Examples:

    # Default 300-presentation symposium (15 classes × 20 students)
    python scripts/seed_large_symposium.py

    # 400-presentation upper-bound case
    python scripts/seed_large_symposium.py --size 400

    # Custom: 250 presentations across 10 classes, 6 rooms, 3 days
    python scripts/seed_large_symposium.py --size 250 --classes 10 --rooms 6 --days 3

    # Inject a few cross-class double-major students (same email in two classes)
    python scripts/seed_large_symposium.py --size 400 --double-majors 5

    # Wipe seeded symposia (matches by name prefix) before inserting
    python scripts/seed_large_symposium.py --replace

After running, the new symposium id is printed. Open the admin UI and run the
scheduler against it, or POST /api/events/schedule with that symposium_id.

Bypasses the API auth layer by writing directly via the Supabase service-role
client (same pattern as scripts/delete_symposia.py).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.supabase_io.client import supabase  # noqa: E402

SEED_NAME_PREFIX = "Seed:"

# ── Defaults sized for the user's stated targets ────────────────────────────
# 300 presentations → 15 classes × 20 students, 5 rooms, 3 days
# 400 presentations → 20 classes × 20 students, 5 rooms, 4 days
_DEFAULT_PROFILES: dict[int, dict[str, int]] = {
    300: {"classes": 15, "rooms": 5, "days": 3},
    400: {"classes": 20, "rooms": 5, "days": 4},
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _build_timeframes(start_date: datetime, days: int) -> list[dict[str, str]]:
    """One 9 AM – 5 PM window per day."""
    out: list[dict[str, str]] = []
    for d in range(days):
        day_start = (start_date + timedelta(days=d)).replace(
            hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        day_end = day_start.replace(hour=17, minute=0)
        out.append({"start_time": _iso(day_start), "end_time": _iso(day_end)})
    return out


def _wipe_existing_seeds() -> int:
    """Delete every symposium whose name starts with SEED_NAME_PREFIX, with cascades."""
    from app.supabase_io.delete import delete_symposium

    resp = (
        supabase.table("symposiums")
        .select("id,name")
        .like("name", f"{SEED_NAME_PREFIX}%")
        .execute()
    )
    rows = resp.data or []
    for r in rows:
        delete_symposium(UUID(str(r["id"])))
    return len(rows)


def _insert_rows(table: str, rows: list[dict[str, object]]) -> None:
    """Chunked insert; supabase-py defaults to ~1000-row payloads, smaller is safer."""
    if not rows:
        return
    BATCH = 200
    for i in range(0, len(rows), BATCH):
        supabase.table(table).insert(rows[i : i + BATCH]).execute()


def seed(
    *,
    name: str,
    n_presentations: int,
    n_classes: int,
    rooms: int,
    days: int,
    duration_minutes: int,
    double_majors: int,
    start_date: datetime,
) -> UUID:
    if n_presentations % n_classes != 0:
        raise SystemExit(
            f"--size {n_presentations} must divide evenly into --classes {n_classes}; "
            f"adjust one of them. {n_presentations} / {n_classes} ≠ integer."
        )
    presentations_per_class = n_presentations // n_classes

    # ── Symposium ───────────────────────────────────────────────────────────
    # `symposiums.created_at` has a DEFAULT but the supabase-py REST client
    # serialises absent columns to explicit NULLs, which trips the NOT NULL —
    # so we set it (and updated_at) ourselves. Same pattern the app handlers use.
    now_iso = datetime.now(timezone.utc).isoformat()
    sym_id = uuid4()
    timeframes = _build_timeframes(start_date, days)
    supabase.table("symposiums").insert({
        "id": str(sym_id),
        "name": name,
        "rooms_available": rooms,
        "room_names": [f"Room {i + 1}" for i in range(rooms)],
        "default_buffer": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }).execute()

    # Symposium-level timeframes are linked via linked_id = symposium_id.
    sym_tf_rows: list[dict[str, object]] = []
    for tf in timeframes:
        sym_tf_rows.append({
            "id": str(uuid4()),
            "linked_id": str(sym_id),
            "start_time": tf["start_time"],
            "end_time": tf["end_time"],
        })
    _insert_rows("timeframes", sym_tf_rows)

    # ── One department holds all classes (keeps the script simple). ─────────
    dept_id = uuid4()
    supabase.table("departments").insert({
        "id": str(dept_id),
        "department_name": "Combined Departments",
        "department_head_name": "Seed Script",
        "email": "seed@hamilton.edu",
        "symposium_id": str(sym_id),
    }).execute()

    # ── Classes (one professor per class). ─────────────────────────────────
    class_rows: list[dict[str, object]] = []
    professor_rows: list[dict[str, object]] = []
    class_ids: list[UUID] = []
    professor_ids_per_class: list[UUID] = []
    for c in range(n_classes):
        class_id = uuid4()
        class_ids.append(class_id)
        class_rows.append({
            "id": str(class_id),
            "name": f"Class {c + 1}",
            "department_id": str(dept_id),
        })
        prof_id = uuid4()
        professor_ids_per_class.append(prof_id)
        professor_rows.append({
            "id": str(prof_id),
            "name": f"Professor {c + 1}",
            "email": f"prof{c + 1}-{sym_id.hex[:6]}@hamilton.edu",
            "class_id": str(class_id),
        })
    _insert_rows("classes", class_rows)
    _insert_rows("professors", professor_rows)

    # ── Students. Each class gets `presentations_per_class` students. ───────
    # Double-majors: optionally inject D students that share an email across
    # two classes — the hierarchical solver should still keep their two
    # presentations from overlapping by virtue of the email-identity map.
    student_rows: list[dict[str, object]] = []
    students_by_class: list[list[UUID]] = []
    for c in range(n_classes):
        ids: list[UUID] = []
        for s in range(presentations_per_class):
            sid = uuid4()
            ids.append(sid)
            student_rows.append({
                "id": str(sid),
                "name": f"Student {c + 1}-{s + 1}",
                "email": f"stu{c + 1}_{s + 1}-{sym_id.hex[:6]}@hamilton.edu",
                "class_id": str(class_ids[c]),
            })
        students_by_class.append(ids)

    # Re-write the email of `double_majors` student rows in classes 1..D so
    # they collide with student rows in class 0. Keeps row count fixed.
    for d in range(min(double_majors, n_classes - 1)):
        target_class = d + 1
        if d >= len(students_by_class[0]) or 0 >= len(students_by_class[target_class]):
            break
        shared_email = f"doublemajor{d + 1}-{sym_id.hex[:6]}@hamilton.edu"
        # Find both rows in `student_rows` and rewrite their emails.
        idx_a = sum(presentations_per_class for _ in range(0)) + d  # row in class 0, slot d
        idx_b = sum(presentations_per_class for _ in range(target_class)) + 0  # row in class target_class, slot 0
        student_rows[idx_a]["email"] = shared_email
        student_rows[idx_b]["email"] = shared_email
    _insert_rows("students", student_rows)

    # ── One presentation per student. Each presentation has exactly one ────
    #    presenting student, so the resource set is (class prof) ∪ {student}.
    presentation_rows: list[dict[str, object]] = []
    presenting_student_rows: list[dict[str, object]] = []
    for c in range(n_classes):
        for s in range(presentations_per_class):
            pres_id = uuid4()
            student_id = students_by_class[c][s]
            presentation_rows.append({
                "id": str(pres_id),
                "title": f"Class {c + 1}, Talk {s + 1}",
                "class_id": str(class_ids[c]),
                "minutes": duration_minutes,
                "buffer": 0,
            })
            presenting_student_rows.append({
                "id": str(uuid4()),
                "presentation_id": str(pres_id),
                "student_id": str(student_id),
            })
    _insert_rows("presentations", presentation_rows)
    _insert_rows("presenting_students", presenting_student_rows)

    return sym_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a synthetic large symposium for scheduler testing."
    )
    parser.add_argument(
        "--size", type=int, default=300,
        help="Number of presentations to seed (default 300; built-in profiles for 300 and 400).",
    )
    parser.add_argument(
        "--classes", type=int, default=None,
        help="Number of classes. Defaults from --size (300→15, 400→20).",
    )
    parser.add_argument(
        "--rooms", type=int, default=None,
        help="Rooms available. Defaults from --size (300→5, 400→5).",
    )
    parser.add_argument(
        "--days", type=int, default=None,
        help="Number of 9 AM–5 PM days. Defaults from --size (300→3, 400→4).",
    )
    parser.add_argument(
        "--duration", type=int, default=15,
        help="Per-presentation duration in minutes (default 15).",
    )
    parser.add_argument(
        "--double-majors", type=int, default=0,
        help="Inject N double-major students (same email across two class rows).",
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="ISO date for day 1 (default: 30 days from today).",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help=f"Wipe existing symposia named with the '{SEED_NAME_PREFIX}' prefix first.",
    )
    args = parser.parse_args()

    profile = _DEFAULT_PROFILES.get(args.size, {})
    n_classes = args.classes or profile.get("classes") or max(1, args.size // 20)
    rooms = args.rooms or profile.get("rooms") or 5
    days = args.days or profile.get("days") or max(2, (args.size * args.duration) // (rooms * 480) + 1)

    if args.start_date:
        start_date = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc)
    else:
        start_date = datetime.now(timezone.utc) + timedelta(days=30)

    if args.replace:
        wiped = _wipe_existing_seeds()
        print(f"Wiped {wiped} prior seed symposium(s).")

    name = f"{SEED_NAME_PREFIX} {args.size} presentations ({n_classes} classes, {rooms} rooms, {days} days)"
    print(f"Seeding {name!r}…")
    t0 = time.perf_counter()
    sym_id = seed(
        name=name,
        n_presentations=args.size,
        n_classes=n_classes,
        rooms=rooms,
        days=days,
        duration_minutes=args.duration,
        double_majors=args.double_majors,
        start_date=start_date,
    )
    elapsed = time.perf_counter() - t0
    print(f"Done in {elapsed:.1f}s.")
    print(f"Symposium ID: {sym_id}")
    total_demand = args.size * args.duration
    total_capacity = rooms * days * 480
    print(
        f"Capacity check: {args.size} × {args.duration} min = {total_demand} min demand "
        f"vs {rooms} rooms × {days} days × 480 min = {total_capacity} min capacity "
        f"({100 * total_demand / total_capacity:.0f}% utilisation)."
    )
    if args.double_majors:
        print(
            f"Injected {args.double_majors} double-major student(s) — same email shared "
            f"between class 1 and one other class. The hierarchical scheduler should "
            f"keep their two presentations from overlapping; the verification sweep "
            f"will surface any miss."
        )


if __name__ == "__main__":
    main()
