from datetime import datetime
from typing import Any, cast
from uuid import UUID

from app.supabase_io import read
from app.supabase_io.supabase_schemas import Presentation, Professor, Student, Symposium, Timeframe

def _rows(data: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], data)


def fetch_symposium(symposium_uuid: UUID) -> Symposium:
    rows = _rows(read.get_symposiums().data)
    return next(Symposium(**r) for r in rows if str(r["id"]) == str(symposium_uuid))


def fetch_symposium_slots(symposium_uuid: UUID) -> list[Timeframe]:
    rows = _rows(read.get_timeframes(linked_id=symposium_uuid).data)
    return sorted([Timeframe(**r) for r in rows], key=lambda t: t.start_time)


def fetch_departments(symposium_uuid: UUID) -> list[UUID]:
    rows = _rows(read.get_departments(symposium_id=symposium_uuid).data)
    return [UUID(str(r["id"])) for r in rows]


def fetch_classes(department_uuids: list[UUID]) -> list[UUID]:
    rows = _rows(read.get_classes(department_id=department_uuids).data)
    return [UUID(str(r["id"])) for r in rows]


def fetch_presentations(class_uuids: list[UUID]) -> list[Presentation]:
    rows = _rows(read.get_presentations(class_id=class_uuids).data)
    return [Presentation(**r) for r in rows]


def fetch_professors(class_uuids: list[UUID]) -> list[Professor]:
    rows = _rows(read.get_professors(class_id=class_uuids).data)
    return [Professor(**r) for r in rows]


def fetch_students(class_uuids: list[UUID]) -> list[Student]:
    rows = _rows(read.get_students(class_id=class_uuids).data)
    return [Student(**r) for r in rows]


def fetch_professor_availability(professors: list[Professor]) -> dict[UUID, set[datetime]]:
    return {
        prof.id: {Timeframe(**r).start_time for r in _rows(read.get_timeframes(linked_id=prof.id).data)}
        for prof in professors
    }


def fetch_student_availability(students: list[Student]) -> dict[UUID, set[datetime]]:
    return {
        student.id: {Timeframe(**r).start_time for r in _rows(read.get_timeframes(linked_id=student.id).data)}
        for student in students
    }

def fetch_presentation_to_professors(presentations: list[Presentation], professors: list[Professor]) -> dict[UUID, list[UUID]]:
    return {
        pres.id: [prof.id for prof in professors if prof.class_id == pres.class_id]
        for pres in presentations
    }

def fetch_presentation_to_students(presentations: list[Presentation], students: list[Student]) -> dict[UUID, list[UUID]]:
    return {
        pres.id: [student.id for student in students if student.presentation_id == pres.id]
        for pres in presentations
    }

# check presentations from the same class are in the same room
def fetch_class_to_presentations(presentations: list[Presentation]) -> dict[UUID, list[UUID]]:
    result: dict[UUID, list[UUID]] = {}
    for pres in presentations:
        result.setdefault(pres.class_id, []).append(pres.id)
    return result


def scheduler_payload(symposium_id: UUID) -> tuple[
    Symposium,
    list[Timeframe],
    list[Presentation],
    dict[UUID, set[datetime]],
    dict[UUID, set[datetime]],
    dict[UUID, list[UUID]],
    dict[UUID, list[UUID]],
    dict[UUID, list[UUID]],
]:
    symposium = fetch_symposium(symposium_id)
    symposium_slots = fetch_symposium_slots(symposium_id)
    department_ids = fetch_departments(symposium_id)
    class_ids = fetch_classes(department_ids)
    presentations = fetch_presentations(class_ids)
    professors = fetch_professors(class_ids)
    students = fetch_students(class_ids)

    return (
        symposium,
        symposium_slots,
        presentations,
        fetch_professor_availability(professors),
        fetch_student_availability(students),
        fetch_presentation_to_professors(presentations, professors),
        fetch_presentation_to_students(presentations, students),
        fetch_class_to_presentations(presentations),
    )
