from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from app.scheduler.cp_sat import solve_schedule
from app.scheduler.models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduleProblem,
    ScheduleResult,
)
from app.supabase_io import read
from app.supabase_io.client import supabase


def _coerce_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"Invalid datetime value: {value!r}")


def _window_rows_to_models(rows: list[dict[str, Any]]) -> tuple[AvailabilityWindow, ...]:
    windows = []
    for row in rows:
        start_time = _coerce_datetime(row["start_time"])
        end_time = _coerce_datetime(row["end_time"])
        if end_time > start_time:
            windows.append(AvailabilityWindow(start=start_time, end=end_time))
    windows.sort(key=lambda window: window.start)

    if not windows:
        return ()

    merged: list[AvailabilityWindow] = [windows[0]]
    for window in windows[1:]:
        current = merged[-1]
        if window.start <= current.end:
            merged[-1] = AvailabilityWindow(
                start=current.start,
                end=max(current.end, window.end),
            )
            continue
        merged.append(window)

    return tuple(merged)


def _get_symposium_row(symposium_id: UUID) -> dict[str, Any]:
    response = (
        supabase.table("symposiums")
        .select("*")
        .eq("id", str(symposium_id))
        .limit(1)
        .execute()
    )
    rows = list(getattr(response, "data", None) or [])
    if not rows:
        raise ValueError(f"Symposium {symposium_id} was not found.")
    return dict(rows[0])


def build_problem_from_symposium(
    symposium_id: str | UUID, slot_minutes: int = 5
) -> ScheduleProblem:
    symposium_uuid = _coerce_uuid(symposium_id)
    symposium_row = _get_symposium_row(symposium_uuid)
    rooms_available = int(symposium_row["rooms_available"])

    symposium_timeframes_resp = read.get_timeframes(linked_id=symposium_uuid)
    symposium_timeframes = list(getattr(symposium_timeframes_resp, "data", None) or [])
    symposium_windows = _window_rows_to_models(symposium_timeframes)
    if not symposium_windows:
        raise ValueError(f"Symposium {symposium_uuid} has no timeframes.")

    departments_resp = read.get_departments(symposium_id=symposium_uuid)
    departments = list(getattr(departments_resp, "data", None) or [])
    department_ids = [UUID(str(row["id"])) for row in departments if row.get("id")]

    classes = []
    if department_ids:
        classes_resp = read.get_classes(department_id=department_ids)
        classes = list(getattr(classes_resp, "data", None) or [])
    class_ids = [UUID(str(row["id"])) for row in classes if row.get("id")]

    professors = []
    presentations = []
    if class_ids:
        professors_resp = read.get_professors(class_id=class_ids)
        professors = list(getattr(professors_resp, "data", None) or [])
        presentations_resp = read.get_presentations(class_id=class_ids)
        presentations = list(getattr(presentations_resp, "data", None) or [])

    professors_by_class: dict[str, list[str]] = defaultdict(list)
    person_ids: set[str] = set()
    for professor in professors:
        professor_id = str(professor["id"])
        class_id = str(professor["class_id"])
        professors_by_class[class_id].append(professor_id)
        person_ids.add(professor_id)

    scheduler_presentations: list[PresentationInput] = []
    for presentation in presentations:
        presentation_id = str(presentation["id"])
        title = str(presentation.get("title") or presentation_id)
        duration_minutes = int(presentation.get("minutes") or 0)
        class_id = str(presentation["class_id"])
        resource_ids: list[str] = list(professors_by_class.get(class_id, []))

        for student in presentation.get("presenting_students", []):
            student_id = str(student["id"])
            resource_ids.append(student_id)
            person_ids.add(student_id)

        scheduler_presentations.append(
            PresentationInput(
                id=presentation_id,
                title=title,
                duration_minutes=duration_minutes,
                resource_ids=tuple(dict.fromkeys(resource_ids)),
            )
        )

    resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}
    if person_ids:
        timeframe_resp = read.get_timeframes(linked_id=[UUID(person_id) for person_id in person_ids])
        timeframe_rows = list(getattr(timeframe_resp, "data", None) or [])
        grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in timeframe_rows:
            grouped_rows[str(row["linked_id"])].append(row)
        for person_id, rows in grouped_rows.items():
            resource_windows[person_id] = _window_rows_to_models(rows)

    return ScheduleProblem(
        symposium_id=str(symposium_uuid),
        rooms_available=rooms_available,
        symposium_windows=symposium_windows,
        presentations=tuple(scheduler_presentations),
        resource_windows=resource_windows,
        slot_minutes=slot_minutes,
    )


def build_schedule_for_symposium(
    symposium_id: str | UUID, slot_minutes: int = 5, time_limit_seconds: float = 10.0
) -> ScheduleResult:
    problem = build_problem_from_symposium(
        symposium_id=symposium_id,
        slot_minutes=slot_minutes,
    )
    return solve_schedule(problem, time_limit_seconds=time_limit_seconds)