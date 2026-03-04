import logging
from uuid import UUID

from app.supabase_io.client import supabase
from app.supabase_io import read

logger = logging.getLogger(__name__)


def rows_affected(response, fallback: int = 0) -> int:
    """Return rows affected from a Supabase response object."""
    if isinstance(response, dict):
        count = response.get("count")
        if isinstance(count, int) and count >= 0:
            return count
        data = response.get("data")
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return 1
        return fallback

    count = getattr(response, "count", None)
    if isinstance(count, int) and count >= 0:
        return count

    data = getattr(response, "data", None)
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return 1

    return fallback


def _merge_counts(target: dict[str, int], source: dict[str, int] | None):
    if not source:
        return
    for table_name, count in source.items():
        if not isinstance(count, int) or count < 0:
            continue
        target[table_name] = target.get(table_name, 0) + count


def _safe_count(value) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def delete_timeframes(linked_id: UUID | list[UUID]):
    del_timeframes_query = supabase.table("timeframes").delete()

    num_deleted = (
        supabase.table("timeframes")
        .select("linked_id", count="exact")
        .eq("linked_id", linked_id)
        .execute()
        .count
    )

    if isinstance(linked_id, UUID):
        del_timeframes_query = del_timeframes_query.eq("linked_id", linked_id)
    elif isinstance(linked_id, list):
        del_timeframes_query = del_timeframes_query.in_("linked_id", linked_id)

    del_timeframes_query.execute()
    logger.info("Deleted %s timeframe(s) for linked_id=%s", num_deleted, linked_id)
    return num_deleted


def delete_student(student_id: UUID | list[UUID]):
    # TODO: Make sure that if the last student is deleted from a presentation, the presentation is deleted as well.
    del_stu_query = supabase.table("students").delete()
    del_presenting_student_query = supabase.table("presenting_students").delete()
    del_prof_request_query = supabase.table("requests").delete()

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
    counts = {
        "students": rows_affected(del_stu_resp),
        "presenting_students": rows_affected(del_presenting_student_resp),
        "prof_requests": rows_affected(del_prof_request_resp),
        "timeframes": deleted_timeframes,
    }
    logger.info("Deleted student(s) %s → %s", student_id, counts)
    return counts


def delete_professor(prof_id: UUID | list[UUID]):
    # TODO: What to do when the last professor in a class/presentation is removed?
    del_prof_query = supabase.table("professors").delete()
    del_prof_request_query = supabase.table("requests").delete()

    if isinstance(prof_id, UUID):
        del_prof_query = del_prof_query.eq("id", prof_id)
        del_prof_request_query = del_prof_request_query.eq("professor_id", prof_id)
    elif isinstance(prof_id, list):
        del_prof_query = del_prof_query.in_("id", prof_id)
        del_prof_request_query = del_prof_request_query.in_("professor_id", prof_id)

    deleted_timeframes = _safe_count(delete_timeframes(prof_id))
    del_prof_resp = del_prof_query.execute()
    del_prof_request_resp = del_prof_request_query.execute()
    counts = {
        "professors": rows_affected(del_prof_resp),
        "prof_requests": rows_affected(del_prof_request_resp),
        "timeframes": deleted_timeframes,
    }
    logger.info("Deleted professor(s) %s → %s", prof_id, counts)
    return counts


def delete_presentation(presentation_id: UUID | list[UUID]):
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
    counts = {
        "presentations": rows_affected(del_pres_resp),
        "presenting_students": rows_affected(del_presenting_student_resp),
        "timeframes": deleted_timeframes,
    }
    logger.info("Deleted presentation(s) %s → %s", presentation_id, counts)
    return counts


def delete_multiple_classes(class_ids: list[UUID]):
    counts: dict[str, int] = {}
    for class_id in class_ids:
        _merge_counts(counts, delete_class(class_id))
    return counts


def delete_class(class_id: UUID | list[UUID]):
    if isinstance(class_id, list):
        return delete_multiple_classes(class_id)

    counts: dict[str, int] = {}

    student_list = read.get_students(class_id=class_id).data
    for student in student_list:
        _merge_counts(counts, delete_student(student_id=UUID(student["id"])))

    prof_list = read.get_professors(class_id=class_id).data
    for professor in prof_list:
        _merge_counts(counts, delete_professor(UUID(professor["id"])))
    pres_list = read.get_presentations(class_id=class_id).data
    for presentation in pres_list:
        _merge_counts(
            counts, delete_presentation(presentation_id=UUID(presentation["id"]))
        )

    del_class_resp = supabase.table("classes").delete().eq("id", class_id).execute()
    counts["classes"] = counts.get("classes", 0) + rows_affected(del_class_resp)
    logger.info("Deleted class %s → %s", class_id, counts)
    return counts


def delete_multiple_departments(department_ids: list[UUID]):
    counts: dict[str, int] = {}
    for department in department_ids:
        _merge_counts(counts, delete_department(department))
    return counts


def delete_department(department_id: UUID | list[UUID]):
    if isinstance(department_id, list):
        return delete_multiple_departments(department_id)

    counts: dict[str, int] = {}

    classes = read.get_classes(department_id).data
    for class_ in classes:
        class_id_raw = class_.get("id")
        if class_id_raw is None:
            continue
        class_id = class_id_raw if isinstance(class_id_raw, UUID) else UUID(str(class_id_raw))
        _merge_counts(counts, delete_class(class_id))

    del_dept_resp = (
        supabase.table("departments").delete().eq("id", department_id).execute()
    )
    counts["departments"] = counts.get("departments", 0) + rows_affected(del_dept_resp)
    logger.info("Deleted department %s → %s", department_id, counts)
    return counts


def delete_symposium(symposium_id: UUID):
    counts: dict[str, int] = {}
    departments = read.get_departments(symposium_id).data
    for department in departments:
        _merge_counts(counts, delete_department(UUID(department["id"])))

    counts["timeframes"] = counts.get("timeframes", 0) + _safe_count(
        delete_timeframes(symposium_id)
    )
    del_symposium_resp = (
        supabase.table("symposiums").delete().eq("id", symposium_id).execute()
    )
    counts["symposiums"] = counts.get("symposiums", 0) + rows_affected(
        del_symposium_resp
    )
    logger.info("Deleted symposium %s → %s", symposium_id, counts)
    return counts
