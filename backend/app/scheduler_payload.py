from datetime import datetime
from uuid import UUID

from app.supabase_io import read
from app.supabase_io.supabase_schemas import Presentation, Professor, Student, Symposium, Timeframe

def fetch_symposium(symposium_uuid: UUID) -> Symposium:
    sym_resp = read.get_symposiums()
    return next(
        Symposium(**s) for s in sym_resp.data if str(s["id"]) == str(symposium_uuid)
    )

def fetch_symposium_slots(symposium_uuid: UUID) -> list[Timeframe]:
    sym_tf_resp = read.get_timeframes(linked_id=symposium_uuid)
    return sorted(
        [Timeframe(**t) for t in sym_tf_resp.data],
        key=lambda t: t.start_time,
    )

def fetch_departments(symposium_uuid: UUID) -> list[UUID]:
    dept_resp = read.get_departments(symposium_id=symposium_uuid)
    return [d["id"] for d in dept_resp.data]

def fetch_classes(department_uuids: list[UUID]) -> list[UUID]:
    class_resp = read.get_classes(department_id=department_uuids)
    return [c["id"] for c in class_resp.data]

def fetch_presentations(class_uuids: list[UUID]) -> list[Presentation]:
    pres_resp = read.get_presentations(class_id=class_uuids)
    return [Presentation(**p) for p in pres_resp.data]

def fetch_professors(class_uuids: list[UUID]) -> list[Professor]:
    prof_resp = read.get_professors(class_id=class_uuids)
    return [Professor(**p) for p in prof_resp.data]

def fetch_students(class_uuids: list[UUID]) -> list[Student]:
    return [Student(**s) for s in read.get_students(class_id=class_uuids).data]

def fetch_professor_availability(professors: list[Professor]) -> dict[UUID, set[datetime]]:
    return {
        prof.id: {Timeframe(**t).start_time for t in read.get_timeframes(linked_id=prof.id).data}
        for prof in professors
    }

def fetch_student_availability(students: list[Student]) -> dict[UUID, set[datetime]]:
    return {
        student.id: {Timeframe(**t).start_time for t in read.get_timeframes(linked_id=student.id).data}
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
