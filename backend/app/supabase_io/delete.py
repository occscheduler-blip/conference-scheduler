import logging
from typing import Any, cast
from uuid import UUID

from postgrest.types import CountMethod

from app.supabase_io import read
from app.supabase_io.client import supabase
from app.utils import force_uuid, rows_affected as _rows_affected

logger = logging.getLogger(__name__)


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


def _to_uuid_list(value: UUID | list[UUID]) -> list[UUID]:
    if isinstance(value, UUID):
        return [value]
    return list(value)


def _collect_ids(rows: list[dict[str, Any]]) -> list[UUID]:
    return [force_uuid(row["id"]) for row in rows if row.get("id") is not None]


def delete_temporary_timeframes(linked_id: UUID | list[UUID]) -> int:
    logger.info("DELETE temporary_timeframes: linked_id=%s", linked_id)
    del_query = supabase.table("temporary_timeframes").delete()
    count_query = supabase.table("temporary_timeframes").select("linked_id", count=CountMethod.exact)

    if isinstance(linked_id, UUID):
        count_query = count_query.eq("linked_id", str(linked_id))
        del_query = del_query.eq("linked_id", str(linked_id))
    else:
        str_ids = [str(uid) for uid in linked_id]
        if not str_ids:
            return 0
        count_query = count_query.in_("linked_id", str_ids)
        del_query = del_query.in_("linked_id", str_ids)

    num_deleted = count_query.execute().count
    if num_deleted is None:
        num_deleted = 0
    del_query.execute()
    return num_deleted


def delete_timeframes(linked_id: UUID | list[UUID]) -> int:
    logger.info("DELETE timeframes: linked_id=%s", linked_id)
    del_timeframes_query = supabase.table("timeframes").delete()
    count_query = supabase.table("timeframes").select("linked_id", count=CountMethod.exact)

    if isinstance(linked_id, UUID):
        count_query = count_query.eq("linked_id", str(linked_id))
        del_timeframes_query = del_timeframes_query.eq("linked_id", str(linked_id))
    else:
        str_ids = [str(uid) for uid in linked_id]
        if not str_ids:
            return 0
        count_query = count_query.in_("linked_id", str_ids)
        del_timeframes_query = del_timeframes_query.in_("linked_id", str_ids)

    num_deleted = count_query.execute().count
    if num_deleted is None:
        num_deleted = 0

    del_timeframes_query.execute()

    return num_deleted


def delete_student(student_id: UUID | list[UUID]) -> dict[str, int]:
    logger.info("DELETE student: student_id=%s", student_id)
    student_ids = _to_uuid_list(student_id)
    counts: dict[str, int] = {
        "students": 0,
        "presenting_students": 0,
        "presentations": 0,
        "requests": 0,
        "timeframes": 0,
    }
    if not student_ids:
        return counts

    str_ids = [str(uid) for uid in student_ids]

    # Record which presentations these students belong to before deleting.
    affected_rows = (
        supabase.table("presenting_students")
        .select("presentation_id")
        .in_("student_id", str_ids)
        .execute()
    )
    affected_pres_ids = list({cast("dict[str, Any]", row)["presentation_id"] for row in (affected_rows.data or [])})

    del_stu_query = supabase.table("students").delete().in_("id", str_ids)
    del_presenting_student_query = (
        supabase.table("presenting_students").delete().in_("student_id", str_ids)
    )
    del_prof_request_query = (
        supabase.table("requests").delete().in_("student_id", str_ids)
    )

    counts["timeframes"] = _safe_count(delete_timeframes(student_ids))
    # Delete child rows first to satisfy FK constraints, then delete the student row(s).
    counts["presenting_students"] = _rows_affected(del_presenting_student_query.execute())
    counts["requests"] = _rows_affected(del_prof_request_query.execute())
    counts["students"] = _rows_affected(del_stu_query.execute())

    # Cascade: delete any presentations that now have no remaining students.
    if affected_pres_ids:
        still_occupied = (
            supabase.table("presenting_students")
            .select("presentation_id")
            .in_("presentation_id", affected_pres_ids)
            .execute()
        )
        occupied_ids = {cast("dict[str, Any]", row)["presentation_id"] for row in (still_occupied.data or [])}
        now_empty = [UUID(str(pid)) for pid in affected_pres_ids if pid not in occupied_ids]
        if now_empty:
            _merge_counts(counts, delete_presentation(now_empty))

    return counts


def delete_professor(prof_id: UUID | list[UUID]) -> dict[str, int]:
    logger.info("DELETE professor: prof_id=%s", prof_id)
    # Note: requests are linked to students (not professors) — no requests cleanup needed here.
    prof_ids = _to_uuid_list(prof_id)
    counts: dict[str, int] = {"professors": 0, "timeframes": 0}
    if not prof_ids:
        return counts

    str_ids = [str(uid) for uid in prof_ids]
    counts["timeframes"] = _safe_count(delete_timeframes(prof_ids))
    del_prof_resp = supabase.table("professors").delete().in_("id", str_ids).execute()
    counts["professors"] = _rows_affected(del_prof_resp)
    return counts


def delete_presentation(presentation_id: UUID | list[UUID]) -> dict[str, int]:
    logger.info("DELETE presentation: presentation_id=%s", presentation_id)
    pres_ids = _to_uuid_list(presentation_id)
    counts: dict[str, int] = {
        "presentations": 0,
        "presenting_students": 0,
        "timeframes": 0,
    }
    if not pres_ids:
        return counts

    str_ids = [str(uid) for uid in pres_ids]
    del_presenting_student_query = (
        supabase.table("presenting_students").delete().in_("presentation_id", str_ids)
    )
    del_pres_query = supabase.table("presentations").delete().in_("id", str_ids)

    counts["timeframes"] = _safe_count(delete_timeframes(pres_ids))
    # Delete child rows first to satisfy FK constraints, then delete the presentation row(s).
    counts["presenting_students"] = _rows_affected(del_presenting_student_query.execute())
    counts["presentations"] = _rows_affected(del_pres_query.execute())
    return counts


def delete_class(class_id: UUID | list[UUID]) -> dict[str, int]:
    logger.info("DELETE class: class_id=%s", class_id)
    class_ids = _to_uuid_list(class_id)
    counts: dict[str, int] = {
        "classes": 0,
        "students": 0,
        "presenting_students": 0,
        "requests": 0,
        "professors": 0,
        "presentations": 0,
        "timeframes": 0,
    }
    if not class_ids:
        return counts

    student_rows = cast(
        list[dict[str, Any]], read.get_students(class_id=class_ids).data or []
    )
    prof_rows = cast(
        list[dict[str, Any]], read.get_professors(class_id=class_ids).data or []
    )
    pres_rows = cast(
        list[dict[str, Any]], read.get_presentations(class_id=class_ids).data or []
    )

    student_ids = _collect_ids(student_rows)
    prof_ids = _collect_ids(prof_rows)
    pres_ids = _collect_ids(pres_rows)

    if student_ids:
        _merge_counts(counts, delete_student(student_ids))
    if prof_ids:
        _merge_counts(counts, delete_professor(prof_ids))
    if pres_ids:
        _merge_counts(counts, delete_presentation(pres_ids))

    del_classes_resp = (
        supabase.table("classes")
        .delete()
        .in_("id", [str(cid) for cid in class_ids])
        .execute()
    )
    counts["classes"] = counts.get("classes", 0) + _rows_affected(del_classes_resp)
    return counts


def delete_department(department_id: UUID | list[UUID]) -> dict[str, int]:
    logger.info("DELETE department: department_id=%s", department_id)
    dept_ids = _to_uuid_list(department_id)
    counts: dict[str, int] = {"departments": 0}
    if not dept_ids:
        return counts

    class_rows = cast(
        list[dict[str, Any]], read.get_classes(department_id=dept_ids).data or []
    )
    class_ids = _collect_ids(class_rows)

    if class_ids:
        _merge_counts(counts, delete_class(class_ids))

    del_dept_resp = (
        supabase.table("departments")
        .delete()
        .in_("id", [str(did) for did in dept_ids])
        .execute()
    )
    counts["departments"] = counts.get("departments", 0) + _rows_affected(del_dept_resp)
    return counts


def delete_symposium(symposium_id: UUID | list[UUID]) -> dict[str, int]:
    logger.info("DELETE symposium: symposium_id=%s", symposium_id)
    sym_ids = _to_uuid_list(symposium_id)
    counts: dict[str, int] = {"symposiums": 0, "timeframes": 0}
    if not sym_ids:
        return counts

    dept_rows = cast(
        list[dict[str, Any]], read.get_departments(symposium_id=sym_ids).data or []
    )
    dept_ids = _collect_ids(dept_rows)

    if dept_ids:
        _merge_counts(counts, delete_department(dept_ids))

    counts["timeframes"] = counts.get("timeframes", 0) + _safe_count(
        delete_timeframes(sym_ids)
    )
    del_symposium_resp = (
        supabase.table("symposiums")
        .delete()
        .in_("id", [str(sid) for sid in sym_ids])
        .execute()
    )
    counts["symposiums"] = counts.get("symposiums", 0) + _rows_affected(
        del_symposium_resp
    )
    return counts
