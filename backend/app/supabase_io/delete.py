from app.supabase_io.client import supabase
from uuid import UUID
from app.supabase_io import read
from postgrest.base_request_builder import APIResponse
from postgrest.types import CountMethod
from typing import cast
from app.utils import force_uuid


def _rows_affected(response: APIResponse | dict[str, object], fallback: int = 0) -> int:
    """Return rows affected from a Supabase response object or dict."""
    if isinstance(response, dict):
        count = response.get("count")
        data = response.get("data")
    else:
        count = getattr(response, "count", None)
        data = getattr(response, "data", None)
    if isinstance(count, int) and count >= 0:
        return count
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return 1
    return fallback


def _merge_counts(target: dict[str, int], source: dict[str, int] | None) -> None:
    if not source:
        return
    for table_name, count in source.items():
        if not isinstance(count, int) or count < 0:
            continue
        target[table_name] = target.get(table_name, 0) + count


def _safe_count(value: object) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def delete_timeframes(linked_id: UUID | list[UUID]) -> int:
    del_timeframes_query = supabase.table("timeframes").delete()

    num_deleted = (
        supabase.table("timeframes")
        .select("linked_id", count=CountMethod.exact)
        .eq("linked_id", linked_id)
        .execute()
        .count
    )
    if num_deleted is None:
        num_deleted = 0

    if isinstance(linked_id, UUID):
        del_timeframes_query = del_timeframes_query.eq("linked_id", linked_id)
    elif isinstance(linked_id, list):
        del_timeframes_query = del_timeframes_query.in_("linked_id", linked_id)

    del_timeframes_resp = del_timeframes_query.execute()

    return num_deleted


def delete_student(student_id: UUID | list[UUID]) -> dict[str, int]:
    # TODO: Make sure that if the last student is deleted from a presentation, the presentation is deleted as well.
    del_stu_query = supabase.table("students").delete()
    del_presenting_student_query = supabase.table("presenting_students").delete()
    del_prof_request_query = supabase.table("prof_requests").delete()

    if isinstance(student_id, UUID):
        del_stu_query = del_stu_query.eq("id", student_id)
        del_presenting_student_query = del_presenting_student_query.eq(
            "student_id", student_id
        )
        del_prof_request_query = del_prof_request_query.eq("student_id", student_id)
    elif isinstance(student_id, list):
        del_stu_query = del_stu_query.in_("id", student_id)
        del_presenting_student_query = del_presenting_student_query.in_(
            "student_id", student_id
        )
        del_prof_request_query = del_prof_request_query.in_("student_id", student_id)

    deleted_timeframes = _safe_count(delete_timeframes(student_id))
    del_stu_resp = del_stu_query.execute()
    del_presenting_student_resp = del_presenting_student_query.execute()
    del_prof_request_resp = del_prof_request_query.execute()
    return {
        "students": _rows_affected(del_stu_resp),
        "presenting_students": _rows_affected(del_presenting_student_resp),
        "prof_requests": _rows_affected(del_prof_request_resp),
        "timeframes": deleted_timeframes,
    }


def delete_professor(prof_id: UUID | list[UUID]) -> dict[str, int]:
    # TODO: What to do when the last professor in a class/presentation is removed?
    del_prof_query = supabase.table("professors").delete()
    del_prof_request_query = supabase.table("prof_requests").delete()

    if isinstance(prof_id, UUID):
        del_prof_query = del_prof_query.eq("id", prof_id)
        del_prof_request_query = del_prof_request_query.eq("professor_id", prof_id)
    elif isinstance(prof_id, list):
        del_prof_query = del_prof_query.in_("id", prof_id)
        del_prof_request_query = del_prof_request_query.in_("professor_id", prof_id)

    deleted_timeframes = _safe_count(delete_timeframes(prof_id))
    del_prof_resp = del_prof_query.execute()
    del_prof_request_resp = del_prof_request_query.execute()
    return {
        "professors": _rows_affected(del_prof_resp),
        "prof_requests": _rows_affected(del_prof_request_resp),
        "timeframes": deleted_timeframes,
    }


def delete_presentation(presentation_id: UUID | list[UUID]) -> dict[str, int]:
    del_pres_query = supabase.table("presentations").delete()
    del_presenting_student_query = supabase.table("presenting_students").delete()

    if isinstance(presentation_id, UUID):
        del_pres_query = del_pres_query.eq("id", presentation_id)
        del_presenting_student_query = del_presenting_student_query.eq(
            "presentation_id", presentation_id
        )
    elif isinstance(presentation_id, list):
        del_pres_query = del_pres_query.in_("id", presentation_id)
        del_presenting_student_query = del_presenting_student_query.in_(
            "presentation_id", presentation_id
        )

    deleted_timeframes = _safe_count(delete_timeframes(presentation_id))
    del_pres_resp = del_pres_query.execute()
    del_presenting_student_resp = del_presenting_student_query.execute()
    return {
        "presentations": _rows_affected(del_pres_resp),
        "presenting_students": _rows_affected(del_presenting_student_resp),
        "timeframes": deleted_timeframes,
    }


def delete_multiple_classes(class_ids: list[UUID]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for class_id in class_ids:
        _merge_counts(counts, delete_class(class_id))
    return counts


def delete_class(class_id: UUID | list[UUID]) -> dict[str, int]:
    if isinstance(class_id, list):
        return delete_multiple_classes(class_id)

    counts: dict[str, int] = {}

    student_list = cast(
        list[dict[str, str | None]], read.get_students(class_id=class_id).data
    )
    for student in student_list:
        if student["id"] is None:
            raise ValueError("Null value for student ID in students table.")
        _merge_counts(counts, delete_student(student_id=force_uuid(student["id"])))

    prof_list = cast(
        list[dict[str, str | None]], read.get_professors(class_id=class_id).data
    )
    for professor in prof_list:
        if professor["id"] is None:
            raise ValueError("Null value for professor ID in professors table.")
        _merge_counts(counts, delete_professor(prof_id=force_uuid(professor["id"])))
    pres_list = cast(
        list[dict[str, str | None]], read.get_presentations(class_id=class_id).data
    )
    for presentation in pres_list:
        if presentation["id"] is None:
            raise ValueError("Null value for presentation ID in presentations table.")
        _merge_counts(counts, delete_presentation(presentation_id=force_uuid(presentation["id"])))

    del_class_resp = supabase.table("classes").delete().eq("id", class_id).execute()
    counts["classes"] = counts.get("classes", 0) + _rows_affected(del_class_resp)
    return counts


def delete_multiple_departments(department_ids: list[UUID]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for department in department_ids:
        _merge_counts(counts, delete_department(department))
    return counts


def delete_department(department_id: UUID | list[UUID]) -> dict[str, int]:
    if isinstance(department_id, list):
        return delete_multiple_departments(department_id)

    counts: dict[str, int] = {}

    classes = cast(list[dict[str, object]], read.get_classes(department_id).data)
    for class_ in classes:
        class_id_raw = class_.get("id")
        if class_id_raw is None:
            continue
        class_id = (
            class_id_raw if isinstance(class_id_raw, UUID) else UUID(str(class_id_raw))
        )
        _merge_counts(counts, delete_class(class_id))

    del_dept_resp = (
        supabase.table("departments").delete().eq("id", department_id).execute()
    )
    counts["departments"] = counts.get("departments", 0) + _rows_affected(del_dept_resp)
    return counts


def delete_symposium(symposium_id: UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    departments = cast(list[dict[str, str]], read.get_departments(symposium_id).data)
    for department in departments:
        _merge_counts(counts, delete_department(UUID(department["id"])))

    counts["timeframes"] = counts.get("timeframes", 0) + _safe_count(
        delete_timeframes(symposium_id)
    )
    del_symposium_resp = (
        supabase.table("symposiums").delete().eq("id", symposium_id).execute()
    )
    counts["symposiums"] = counts.get("symposiums", 0) + _rows_affected(
        del_symposium_resp
    )
    return counts
