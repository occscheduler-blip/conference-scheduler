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

    return query.execute()


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