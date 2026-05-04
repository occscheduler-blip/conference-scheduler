import logging
from typing import Any, cast
from uuid import UUID

from postgrest.base_request_builder import APIResponse

from app.supabase_io.client import supabase

logger = logging.getLogger(__name__)


def get_symposiums() -> APIResponse:
    resp = supabase.table("symposiums").select("*").execute()
    return resp


def get_departments(symposium_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("departments").select("*")

    if symposium_id:
        if isinstance(symposium_id, UUID):
            query = query.eq("symposium_id", str(symposium_id))
        elif isinstance(symposium_id, list):
            query = query.in_("symposium_id", [str(uid) for uid in symposium_id])
        else:
            raise ValueError("symposium_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_classes(department_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("classes").select("*")

    if department_id:
        if isinstance(department_id, UUID):
            query = query.eq("department_id", str(department_id))
        elif isinstance(department_id, list):
            query = query.in_("department_id", [str(uid) for uid in department_id])
        else:
            raise ValueError("department_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_students(class_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("students").select("*")

    if class_id:
        if isinstance(class_id, UUID):
            query = query.eq("class_id", str(class_id))
        elif isinstance(class_id, list):
            query = query.in_("class_id", [str(uid) for uid in class_id])
        else:
            raise ValueError("class_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_professors(class_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("professors").select("*")

    if class_id:
        if isinstance(class_id, UUID):
            query = query.eq("class_id", str(class_id))
        elif isinstance(class_id, list):
            query = query.in_("class_id", [str(uid) for uid in class_id])
        else:
            raise ValueError("class_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_presentations(
    class_id: UUID | list[UUID] | None = None,
) -> APIResponse:
    query = supabase.table("presentations").select(
        "*, presenting_students(students(*))"
    )

    if class_id:
        if isinstance(class_id, UUID):
            query = query.eq("class_id", str(class_id))
        elif isinstance(class_id, list):
            query = query.in_("class_id", [str(uid) for uid in class_id])
        else:
            raise ValueError("class_id must be a UUID or list of UUIDs.")

    resp = query.execute()
    rows = cast(list[dict[str, Any]], resp.data or [])
    for presentation in rows:
        joined = presentation.get("presenting_students") or []
        presentation["presenting_students"] = [
            row["students"]
            for row in joined
            if isinstance(row, dict) and row.get("students")
        ]
    return resp


def get_presenting_students(
    presentation_id: UUID | list[UUID] | None = None,
) -> APIResponse:
    query = supabase.table("presenting_students").select("*")

    if presentation_id:
        if isinstance(presentation_id, UUID):
            query = query.eq("presentation_id", str(presentation_id))
        elif isinstance(presentation_id, list):
            query = query.in_("presentation_id", [str(uid) for uid in presentation_id])
        else:
            raise ValueError("presentation_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_temporary_timeframes(linked_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("temporary_timeframes").select("*")

    if linked_id:
        if isinstance(linked_id, UUID):
            query = query.eq("linked_id", str(linked_id))
        elif isinstance(linked_id, list):
            query = query.in_("linked_id", [str(uid) for uid in linked_id])
        else:
            raise ValueError("linked_id must be a UUID or list of UUIDs.")

    return query.execute()


def get_timeframes(linked_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("timeframes").select("*")

    if linked_id:
        if isinstance(linked_id, UUID):
            query = query.eq("linked_id", str(linked_id))
        elif isinstance(linked_id, list):
            query = query.in_("linked_id", [str(uid) for uid in linked_id])
        else:
            raise ValueError("linked_id must be a UUID or list of UUIDs.")

    return query.execute()


def _first_row(resp: APIResponse) -> dict[str, Any] | None:
    rows = cast(list[dict[str, Any]], resp.data or [])
    return rows[0] if rows else None


def resolve_symposium_for_linked(linked_id: str | UUID) -> str | None:
    """Resolve a polymorphic linked_id to its owning symposium id.

    Accepts the id of a symposium, department, class, professor, student,
    or presentation and walks the FK chain back to the symposium so the
    caller can take a per-symposium advisory lock.
    """
    s = str(linked_id)
    if _first_row(supabase.table("symposiums").select("id").eq("id", s).limit(1).execute()):
        return s
    row = _first_row(
        supabase.table("departments").select("symposium_id").eq("id", s).limit(1).execute()
    )
    if row is not None:
        sym = row.get("symposium_id")
        return str(sym) if sym else None
    row = _first_row(
        supabase.table("classes").select("department_id").eq("id", s).limit(1).execute()
    )
    if row is not None:
        dept_id = row.get("department_id")
        return _symposium_for_department(str(dept_id)) if dept_id else None
    for table in ("professors", "students", "presentations"):
        row = _first_row(
            supabase.table(table).select("class_id").eq("id", s).limit(1).execute()
        )
        if row is not None:
            class_id = row.get("class_id")
            if not class_id:
                return None
            return _symposium_for_class(str(class_id))
    return None


def _symposium_for_department(department_id: str) -> str | None:
    row = _first_row(
        supabase.table("departments")
        .select("symposium_id")
        .eq("id", department_id)
        .limit(1)
        .execute()
    )
    if row is None:
        return None
    sym = row.get("symposium_id")
    return str(sym) if sym else None


def _symposium_for_class(class_id: str) -> str | None:
    row = _first_row(
        supabase.table("classes")
        .select("department_id")
        .eq("id", class_id)
        .limit(1)
        .execute()
    )
    if row is None:
        return None
    dept_id = row.get("department_id")
    if not dept_id:
        return None
    return _symposium_for_department(str(dept_id))


def get_requests(student_id: UUID | list[UUID] | None = None) -> APIResponse:
    query = supabase.table("requests").select("*")

    if student_id:
        if isinstance(student_id, UUID):
            query = query.eq("student_id", str(student_id))
        elif isinstance(student_id, list):
            query = query.in_("student_id", [str(uid) for uid in student_id])
        else:
            raise ValueError("student_id must be a UUID or list of UUIDs.")

    return query.execute()
