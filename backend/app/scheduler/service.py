from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from app.scheduler.cp_sat import SolveSchedule

logger = logging.getLogger(__name__)
from app.scheduler.models import (
    AvailabilityTimeframe,
    PresentationInput,
    ScheduleConstraints,
    ScheduleData,
    ScheduleResult,
)
from app.supabase_io import read
from app.supabase_io.client import supabase
from app.utils import parse_app_datetime


def _CoerceUuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _CoerceDatetime(value: object) -> datetime:
    return parse_app_datetime(value)


def _AssignmentsWithinSymposiumTimeframes(
    schedule_data: ScheduleData,
    result: ScheduleResult,
) -> bool:
    return all(
        any(
            assignment.start >= timeframe.start and assignment.end <= timeframe.end
            for timeframe in schedule_data.symposium_timeframes
        )
        for assignment in result.assignments
    )


def _TimeframeRowsToModels(rows: list[dict[str, Any]]) -> tuple[AvailabilityTimeframe, ...]:
    timeframes = []
    for row in rows:
        start_time = _CoerceDatetime(row["start_time"])
        end_time = _CoerceDatetime(row["end_time"])
        if end_time > start_time:
            timeframes.append(AvailabilityTimeframe(start=start_time, end=end_time))
    timeframes.sort(key=lambda timeframe: timeframe.start)

    if not timeframes:
        return ()

    merged: list[AvailabilityTimeframe] = [timeframes[0]]
    for timeframe in timeframes[1:]:
        current = merged[-1]
        if timeframe.start <= current.end:
            merged[-1] = AvailabilityTimeframe(
                start=current.start,
                end=max(current.end, timeframe.end),
            )
            continue
        merged.append(timeframe)

    return tuple(merged)


def _GetSymposiumRow(symposium_id: UUID) -> dict[str, Any]:
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


def BuildScheduleDataFromSymposium(
    symposium_id: str | UUID,
    slot_minutes: int = 5,
    constraints: ScheduleConstraints | None = None,
) -> ScheduleData:
    if constraints is None:
        constraints = ScheduleConstraints()
    logger.info("Building schedule data for symposium_id=%s  slot_minutes=%d", symposium_id, slot_minutes)
    t_total = time.perf_counter()
    symposium_uuid = _CoerceUuid(symposium_id)

    t = time.perf_counter()
    symposium_row = _GetSymposiumRow(symposium_uuid)
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
    class_to_department: dict[str, str] = {
        str(row["id"]): str(row["department_id"])
        for row in classes
        if row.get("id") and row.get("department_id")
    }

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
                department_id=class_to_department.get(class_id, ""),
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

    symposium_timeframes = _TimeframeRowsToModels(grouped_rows.get(str(symposium_uuid), []))
    if not symposium_timeframes:
        raise ValueError(f"Symposium {symposium_uuid} has no timeframes.")

    resource_timeframes: dict[str, tuple[AvailabilityTimeframe, ...]] = {}
    soft_resource_timeframes: dict[str, tuple[AvailabilityTimeframe, ...]] = {}
    for linked_id, rows in grouped_rows.items():
        if linked_id == str(symposium_uuid):
            continue
        timeframes = _TimeframeRowsToModels(rows)
        if linked_id in professor_ids and constraints.professor_availability == "hard":
            resource_timeframes[linked_id] = timeframes
        elif linked_id in professor_ids and constraints.professor_availability == "soft":
            soft_resource_timeframes[linked_id] = timeframes
        elif linked_id in student_ids and constraints.student_availability == "hard":
            resource_timeframes[linked_id] = timeframes
        elif linked_id in student_ids and constraints.student_availability == "soft":
            soft_resource_timeframes[linked_id] = timeframes
        else:
            continue

    # Professors with no timeframes are treated as fully available.
    for id in professor_ids:
        if id not in resource_timeframes:
            resource_timeframes[id] = symposium_timeframes

    # Do the same for students
    for id in student_ids:
        if id not in resource_timeframes:
            resource_timeframes[id] = symposium_timeframes

    logger.info(
        "Schedule data built: rooms=%d  presentations=%d  professors=%d  students=%d  timeframes=%d  total=%.3fs",
        rooms_available, len(scheduler_presentations), len(professor_ids), len(student_ids), len(symposium_timeframes),
        time.perf_counter() - t_total,
    )
    return ScheduleData(
        symposium_id=str(symposium_uuid),
        rooms_available=rooms_available,
        symposium_timeframes=symposium_timeframes,
        presentations=tuple(scheduler_presentations),
        resource_timeframes=resource_timeframes,
        soft_resource_timeframes=soft_resource_timeframes,
        professor_resource_ids=tuple(sorted(professor_ids)),
        slot_minutes=slot_minutes,
        constraints=constraints,
    )


def BuildProblemFromSymposium(
    symposium_id: str | UUID,
    slot_minutes: int = 5,
    constraints: ScheduleConstraints | None = None,
) -> ScheduleData:
    return BuildScheduleDataFromSymposium(
        symposium_id=symposium_id,
        slot_minutes=slot_minutes,
        constraints=constraints,
    )


def _SaveAssignments(
    result: ScheduleResult,
    presentation_ids_to_reset: tuple[str, ...],
    symposium_id: str,
) -> None:
    from app.supabase_io import delete, write

    logger.info("Saving %d schedule assignments to temporary tables", len(result.assignments))
    # Clear existing draft assignments for every presentation in the symposium so
    # anything the solver leaves unscheduled is reflected in the DB/UI.
    presentation_ids = [UUID(pid) for pid in presentation_ids_to_reset]
    if presentation_ids:
        delete.delete_temporary_timeframes(presentation_ids)
        write.update_column_by_ids(
            "presentations", "temporary_room", {pid: None for pid in presentation_ids}
        )

    timeframe_rows: list[dict[str, str | int | UUID | datetime | date | None]] = []
    room_by_presentation: dict[UUID, str | int | None] = {}
    for assignment in result.assignments:
        timeframe_rows.append({
            "id": uuid4(),
            "linked_id": UUID(assignment.presentation_id),
            "start_time": assignment.start.isoformat(),
            "end_time": assignment.end.isoformat(),
            "symposium_id": UUID(symposium_id),
        })
        room_by_presentation[UUID(assignment.presentation_id)] = assignment.room_index

    if room_by_presentation:
        write.update_column_by_ids("presentations", "temporary_room", room_by_presentation)

    if timeframe_rows:
        write.insert("temporary_timeframes", timeframe_rows)
    logger.info("Draft schedule assignments saved successfully")


def BuildScheduleForSymposium(
    symposium_id: str | UUID,
    slot_minutes: int = 5,
    time_limit_seconds: float = 30.0,
    constraints: ScheduleConstraints | None = None,
) -> ScheduleResult:
    schedule_data = BuildScheduleDataFromSymposium(
        symposium_id=symposium_id,
        slot_minutes=slot_minutes,
        constraints=constraints,
    )
    result = SolveSchedule(schedule_data, time_limit_seconds=time_limit_seconds)
    if result.status in ("optimal", "feasible") and not _AssignmentsWithinSymposiumTimeframes(schedule_data, result):
        logger.error("Scheduler returned an assignment outside the symposium timeframes: symposium_id=%s", symposium_id)
        return ScheduleResult(
            status="invalid",
            assignments=(),
            unscheduled_presentations=tuple(p.id for p in schedule_data.presentations),
            diagnostics=("Scheduler produced an assignment outside the symposium timeframes.",),
        )
    if result.status in ("optimal", "feasible"):
        _SaveAssignments(
            result,
            tuple(p.id for p in schedule_data.presentations),
            schedule_data.symposium_id,
        )
    else:
        logger.warning("Scheduler did not find a solution: status=%s", result.status)
    return result


build_schedule_data_from_symposium = BuildScheduleDataFromSymposium
build_problem_from_symposium = BuildProblemFromSymposium
build_schedule_for_symposium = BuildScheduleForSymposium
