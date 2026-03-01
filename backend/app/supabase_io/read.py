from types import SimpleNamespace
from app.supabase_io.client import supabase
from uuid import UUID


def get_symposiums():
    resp = supabase.table("symposiums").select("*").execute()
    return resp


def get_departments(symposium_id: UUID | None = None):
    query = supabase.table("departments").select("*")
    if symposium_id:
        query = query.eq("symposium_id", symposium_id)
    return query.execute()


def get_classes(department_id: UUID | list[UUID] | None = None):
    query = supabase.table("classes").select("*")

    if department_id:
        if isinstance(department_id, UUID):
            query = query.eq("department_id", department_id)
        elif isinstance(department_id, list):
            query = query.in_("department_id", department_id)
        else:
            raise ValueError("department_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_students(class_id: UUID | list[UUID] | None = None):
    query = supabase.table("students").select("*")

    if class_id:
        if isinstance(class_id, UUID):
            query = query.eq("class_id", class_id)
        elif isinstance(class_id, list):
            query = query.in_("class_id", class_id)
        else:
            raise ValueError("class_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_professors(class_id: UUID | list[UUID] | None = None):
    query = supabase.table("professors").select("*")

    if class_id:
        if isinstance(class_id, UUID):
            query = query.eq("class_id", class_id)
        elif isinstance(class_id, list):
            query = query.in_("class_id", class_id)
        else:
            raise ValueError("class_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_presentations(class_id: UUID | list[UUID] | None = None):
    query = supabase.table("presentations").select("*")

    if class_id:
        if isinstance(class_id, UUID):
            query = query.eq("class_id", class_id)
        elif isinstance(class_id, list):
            query = query.in_("class_id", class_id)
        else:
            raise ValueError("class_id must be a UUID or list of UUIDs.")

    presentations_resp = query.execute()
    presentations = list(presentations_resp.data or [])

    presentation_ids = [presentation["id"] for presentation in presentations if "id" in presentation]
    if not presentation_ids:
        return presentations_resp

    presenting_students_resp = (
        supabase.table("presenting_students")
        .select("*")
        .in_("presentation_id", presentation_ids)
        .execute()
    )
    presenting_rows = list(presenting_students_resp.data or [])

    student_ids = [row["student_id"] for row in presenting_rows if "student_id" in row]
    students_by_id = {}
    if student_ids:
        students_resp = (
            supabase.table("students").select("*").in_("id", student_ids).execute()
        )
        students_by_id = {
            student["id"]: student for student in (students_resp.data or []) if "id" in student
        }

    presenting_by_presentation: dict[UUID, list[dict]] = {}
    for row in presenting_rows:
        presentation_id = row.get("presentation_id")
        if presentation_id is None:
            continue
        student = students_by_id.get(row.get("student_id"))
        if student is not None:
            presenting_by_presentation.setdefault(presentation_id, []).append(student)

    enriched_presentations = []
    for presentation in presentations:
        presentation_id = presentation.get("id")
        enriched_presentation = dict(presentation)
        enriched_presentation["presenting_students"] = presenting_by_presentation.get(
            presentation_id, []
        )
        enriched_presentations.append(enriched_presentation)

    return SimpleNamespace(data=enriched_presentations, count=len(enriched_presentations))


def get_presenting_students(presentation_id: UUID | list[UUID] | None = None):
    query = supabase.table("presenting_students").select("*")

    if presentation_id:
        if isinstance(presentation_id, UUID):
            query = query.eq("presentation_id", presentation_id)
        elif isinstance(presentation_id, list):
            query = query.in_("presentation_id", presentation_id)
        else:
            raise ValueError("presentation_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_timeframes(linked_id: UUID | list[UUID] | None = None):
    query = supabase.table("timeframes").select("*")

    if linked_id:
        if isinstance(linked_id, UUID):
            query = query.eq("linked_id", linked_id)
        elif isinstance(linked_id, list):
            query = query.in_("linked_id", linked_id)
        else:
            raise ValueError("linked_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_prof_requests(
    student_id: UUID | list[UUID] | None = None,
    professor_id: UUID | list[UUID] | None = None,
):
    query = supabase.table("prof_requests").select("*")

    if student_id:
        if isinstance(student_id, UUID):
            query = query.eq("student_id", student_id)
        elif isinstance(student_id, list):
            query = query.in_("student_id", student_id)
        else:
            raise ValueError("student_id must be a UUID or list of UUIDs.")

    if professor_id:
        if isinstance(professor_id, UUID):
            query = query.eq("professor_id", professor_id)
        elif isinstance(professor_id, list):
            query = query.in_("professor_id", professor_id)
        else:
            raise ValueError("professor_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_requests(student_id: UUID | list[UUID] | None = None):
    query = supabase.table("requests").select("*")

    if student_id:
        if isinstance(student_id, UUID):
            query = query.eq("student_id", student_id)
        elif isinstance(student_id, list):
            query = query.in_("student_id", student_id)
        else:
            raise ValueError("student_id must be a UUID or list of UUIDs.")

    return query.execute()
