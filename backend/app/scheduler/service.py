from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from app.scheduler.cp_sat import solve_schedule

logger = logging.getLogger(__name__)
from app.scheduler.models import (
    AvailabilityWindow,
    PresentationInput,
    ScheduleConstraints,
    ScheduleProblem,
    ScheduleResult,
)
from app.supabase_io import read
from app.supabase_io.client import supabase
from app.utils import parse_app_datetime


def _coerce_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _coerce_datetime(value: object) -> datetime:
    return parse_app_datetime(value)


def _assignments_within_symposium_windows(
    problem: ScheduleProblem,
    result: ScheduleResult,
) -> bool:
    return all(
        any(
            assignment.start >= window.start and assignment.end <= window.end
            for window in problem.symposium_windows
        )
        for assignment in result.assignments
    )


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
    symposium_id: str | UUID,
    slot_minutes: int = 5,
    constraints: ScheduleConstraints | None = None,
) -> ScheduleProblem:
    if constraints is None:
        constraints = ScheduleConstraints()
    logger.info("Building schedule problem for symposium_id=%s  slot_minutes=%d", symposium_id, slot_minutes)
    t_total = time.perf_counter()
    symposium_uuid = _coerce_uuid(symposium_id)

    t = time.perf_counter()
    symposium_row = _get_symposium_row(symposium_uuid)
    logger.info("[setup-timing] symposium_row: %.3fs", time.perf_counter() - t)
    rooms_available = int(symposium_row["rooms_available"])
    symposium_default_buffer = int(symposium_row.get("default_buffer") or 0)

    t = time.perf_counter()
    departments_resp = read.get_departments(symposium_id=symposium_uuid)
    logger.info("[setup-timing] get_departments: %.3fs", time.perf_counter() - t)
    departments = list(getattr(departments_resp, "data", None) or [])
    department_ids = [UUID(str(row["id"])) for row in departments if row.get("id")]

    classes = []
    if department_ids:
        t = time.perf_counter()
        classes_resp = read.get_classes(department_id=department_ids)
        logger.info("[setup-timing] get_classes: %.3fs", time.perf_counter() - t)
        classes = list(getattr(classes_resp, "data", None) or [])
    class_ids = [UUID(str(row["id"])) for row in classes if row.get("id")]

    professors = []
    presentations = []
    if class_ids:
        t = time.perf_counter()
        professors_resp = read.get_professors(class_id=class_ids)
        logger.info("[setup-timing] get_professors: %.3fs", time.perf_counter() - t)
        professors = list(getattr(professors_resp, "data", None) or [])
        t = time.perf_counter()
        presentations_resp = read.get_presentations(class_id=class_ids)
        logger.info("[setup-timing] get_presentations: %.3fs", time.perf_counter() - t)
        presentations = list(getattr(presentations_resp, "data", None) or [])

    professors_by_class: dict[str, list[str]] = defaultdict(list)
    person_ids: set[str] = set()
    professor_ids: set[str] = set()
    student_ids: set[str] = set()
    for professor in professors:
        professor_id = str(professor["id"])
        class_id = str(professor["class_id"])
        professors_by_class[class_id].append(professor_id)
        person_ids.add(professor_id)
        professor_ids.add(professor_id)

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
            student_ids.add(student_id)

        scheduler_presentations.append(
            PresentationInput(
                id=presentation_id,
                title=title,
                duration_minutes=duration_minutes,
                buffer_minutes=int(presentation["buffer"] if presentation.get("buffer") is not None else symposium_default_buffer),
                class_id=class_id,
                resource_ids=tuple(dict.fromkeys(resource_ids)),
            )
        )

    all_linked_ids: list[UUID] = [symposium_uuid]
    all_linked_ids.extend(UUID(pid) for pid in person_ids)
    t = time.perf_counter()
    timeframe_resp = read.get_timeframes(linked_id=all_linked_ids)
    logger.info("[setup-timing] get_timeframes (%d ids): %.3fs", len(all_linked_ids), time.perf_counter() - t)
    timeframe_rows = list(getattr(timeframe_resp, "data", None) or [])
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in timeframe_rows:
        grouped_rows[str(row["linked_id"])].append(row)

    symposium_windows = _window_rows_to_models(grouped_rows.get(str(symposium_uuid), []))
    if not symposium_windows:
        raise ValueError(f"Symposium {symposium_uuid} has no timeframes.")

    resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}
    soft_resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = {}
    for linked_id, rows in grouped_rows.items():
        if linked_id == str(symposium_uuid):
            continue
        windows = _window_rows_to_models(rows)
        if linked_id in professor_ids and constraints.professor_availability == "hard":
            resource_windows[linked_id] = windows
        elif linked_id in professor_ids and constraints.professor_availability == "soft":
            soft_resource_windows[linked_id] = windows
        elif linked_id in student_ids and constraints.student_availability == "hard":
            resource_windows[linked_id] = windows
        elif linked_id in student_ids and constraints.student_availability == "soft":
            soft_resource_windows[linked_id] = windows

    # Professors with no timeframes are treated as fully available.
    for id in professor_ids:
        if id not in resource_windows:
            resource_windows[id] = symposium_windows

    # Do the same for students
    for id in student_ids:
        if id not in resource_windows:
            resource_windows[id] = symposium_windows

    logger.info(
        "Schedule problem built: rooms=%d  presentations=%d  professors=%d  students=%d  windows=%d  total=%.3fs",
        rooms_available, len(scheduler_presentations), len(professor_ids), len(student_ids), len(symposium_windows),
        time.perf_counter() - t_total,
    )
    return ScheduleProblem(
        symposium_id=str(symposium_uuid),
        rooms_available=rooms_available,
        symposium_windows=symposium_windows,
        presentations=tuple(scheduler_presentations),
        resource_windows=resource_windows,
        soft_resource_windows=soft_resource_windows,
        professor_resource_ids=tuple(sorted(professor_ids)),
        slot_minutes=slot_minutes,
        constraints=constraints,
    )


def _save_assignments(
    result: ScheduleResult,
    presentation_ids_to_reset: tuple[str, ...],
) -> None:
    from app.supabase_io import delete, write

    logger.info("Saving %d schedule assignments", len(result.assignments))
    # Clear existing assignments for every presentation in the symposium so
    # anything the solver leaves unscheduled is reflected in the DB/UI.
    presentation_ids = [UUID(pid) for pid in presentation_ids_to_reset]
    if presentation_ids:
        delete.delete_timeframes(presentation_ids)
        for pid in presentation_ids:
            supabase.table("presentations").update(
                {"room": None}
            ).eq("id", str(pid)).execute()

    timeframe_rows: list[dict[str, str | int | UUID | datetime | date | None]] = []
    for assignment in result.assignments:
        timeframe_rows.append({
            "id": uuid4(),
            "linked_id": UUID(assignment.presentation_id),
            "start_time": assignment.start.isoformat(),
            "end_time": assignment.end.isoformat(),
        })
        supabase.table("presentations").update({
            "room": assignment.room_index,
        }).eq("id", assignment.presentation_id).execute()

    if timeframe_rows:
        write.insert("timeframes", timeframe_rows)
    logger.info("Schedule assignments saved successfully")


def build_schedule_for_symposium(
    symposium_id: str | UUID,
    slot_minutes: int = 5,
    time_limit_seconds: float = 30.0,
    constraints: ScheduleConstraints | None = None,
) -> ScheduleResult:
    problem = build_problem_from_symposium(
        symposium_id=symposium_id,
        slot_minutes=slot_minutes,
        constraints=constraints,
    )
    result = solve_schedule(problem, time_limit_seconds=time_limit_seconds)
    if result.status in ("optimal", "feasible") and not _assignments_within_symposium_windows(problem, result):
        logger.error("Scheduler returned an assignment outside the symposium windows: symposium_id=%s", symposium_id)
        return ScheduleResult(
            status="invalid",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in problem.presentations),
            diagnostics=("Scheduler produced an assignment outside the symposium windows.",),
        )
    if result.status in ("optimal", "feasible"):
        _save_assignments(
            result,
            tuple(p.id for p in problem.presentations),
        )
    else:
        logger.warning("Scheduler did not find a solution: status=%s", result.status)
    return result
