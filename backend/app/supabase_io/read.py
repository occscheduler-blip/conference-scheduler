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
    def _filter_by_class(query: Any) -> Any:
        if not class_id:
            return query
        if isinstance(class_id, UUID):
            return query.eq("class_id", str(class_id))
        if isinstance(class_id, list):
            return query.in_("class_id", [str(uid) for uid in class_id])
        raise ValueError("class_id must be a UUID or list of UUIDs.")

    resp = _filter_by_class(
        supabase.table("presentations").select("*, presenting_students(students(*))")
    ).execute()
    rows = cast(list[dict[str, Any]], resp.data or [])
    for presentation in rows:
        joined = presentation.get("presenting_students") or []
        presentation["presenting_students"] = [
            row["students"]
            for row in joined
            if isinstance(row, dict) and row.get("students")
        ]
        presentation["assigned_professors"] = []

    presentation_ids = [str(row["id"]) for row in rows if row.get("id")]
    if not presentation_ids:
        return resp

    try:
        assignment_resp = (
            supabase.table("presentation_professors")
            .select("*")
            .in_("presentation_id", presentation_ids)
            .execute()
        )
        assignment_rows = cast(list[dict[str, Any]], assignment_resp.data or [])
        professor_ids = sorted({
            str(row["professor_id"])
            for row in assignment_rows
            if row.get("professor_id")
        })
        professor_by_id: dict[str, dict[str, Any]] = {}
        if professor_ids:
            professor_resp = (
                supabase.table("professors")
                .select("*")
                .in_("id", professor_ids)
                .execute()
            )
            professor_by_id = {
                str(row["id"]): row
                for row in cast(list[dict[str, Any]], professor_resp.data or [])
                if row.get("id")
            }
        presentation_by_id = {str(row["id"]): row for row in rows if row.get("id")}
        for assignment in assignment_rows:
            presentation = presentation_by_id.get(str(assignment.get("presentation_id", "")))
            professor = professor_by_id.get(str(assignment.get("professor_id", "")))
            if presentation is not None and professor is not None:
                presentation["assigned_professors"].append(professor)
    except Exception as exc:
        logger.warning(
            "presentation_professors table is not available; loading presentations without assigned professors: %s",
            exc,
        )
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
