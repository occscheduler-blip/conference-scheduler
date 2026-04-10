from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import os
from uuid import UUID


def _load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_backend_env()

from app.supabase_io import delete
from app.supabase_io.client import supabase
from app.utils import parse_app_datetime


def _parse(value: object) -> datetime:
    return parse_app_datetime(value)


def find_out_of_window_assignments() -> list[dict[str, object]]:
    symposiums = {
        row["id"]: row
        for row in supabase.table("symposiums").select("id,name").execute().data or []
    }
    departments = supabase.table("departments").select("id,symposium_id").execute().data or []
    classes = supabase.table("classes").select("id,department_id").execute().data or []
    presentations = (
        supabase.table("presentations").select("id,title,class_id,room").execute().data or []
    )
    timeframes = (
        supabase.table("timeframes").select("id,linked_id,start_time,end_time").execute().data or []
    )

    symposium_by_department = {row["id"]: row["symposium_id"] for row in departments}
    symposium_by_class = {
        row["id"]: symposium_by_department.get(row["department_id"])
        for row in classes
    }

    windows_by_symposium: dict[str, list[dict[str, object]]] = defaultdict(list)
    for timeframe in timeframes:
        linked_id = str(timeframe["linked_id"])
        if linked_id in symposiums:
            windows_by_symposium[linked_id].append(timeframe)

    timeframe_by_presentation = {
        str(timeframe["linked_id"]): timeframe
        for timeframe in timeframes
        if str(timeframe["linked_id"]) not in symposiums
    }

    invalid: list[dict[str, object]] = []
    for presentation in presentations:
        if presentation.get("room") is None:
            continue
        presentation_id = str(presentation["id"])
        timeframe = timeframe_by_presentation.get(presentation_id)
        if not timeframe:
            continue

        symposium_id = symposium_by_class.get(str(presentation["class_id"]))
        windows = windows_by_symposium.get(str(symposium_id), [])
        if not windows:
            continue

        start = _parse(timeframe["start_time"])
        end = _parse(timeframe["end_time"])
        within = any(
            start >= _parse(window["start_time"]) and end <= _parse(window["end_time"])
            for window in windows
        )
        if within:
            continue

        invalid.append(
            {
                "presentation_id": presentation_id,
                "title": presentation.get("title") or presentation_id,
                "room": presentation["room"],
                "start_time": timeframe["start_time"],
                "end_time": timeframe["end_time"],
                "symposium_id": symposium_id,
                "symposium_name": symposiums.get(str(symposium_id), {}).get("name"),
            }
        )

    return invalid


def repair_out_of_window_assignments(*, apply: bool) -> int:
    invalid = find_out_of_window_assignments()
    if not invalid:
        print("No out-of-window assignments found.")
        return 0

    print(f"Found {len(invalid)} out-of-window assignment(s).")
    for row in invalid:
        print(
            f"- {row['title']} ({row['presentation_id']}): room={row['room']} "
            f"{row['start_time']} -> {row['end_time']} symposium={row['symposium_name']}"
        )

    if not apply:
        print("Dry run only. Re-run with --apply to clear these assignments.")
        return len(invalid)

    presentation_ids = [UUID(str(row["presentation_id"])) for row in invalid]
    delete.delete_timeframes(presentation_ids)
    for presentation_id in presentation_ids:
        supabase.table("presentations").update({"room": None}).eq("id", str(presentation_id)).execute()

    print(f"Cleared {len(presentation_ids)} invalid assignment(s).")
    return len(invalid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clear presentation assignments that fall outside symposium windows."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually clear invalid assignments instead of running a dry run.",
    )
    args = parser.parse_args()
    repair_out_of_window_assignments(apply=args.apply)
