"""Optional nested data fetching for GET endpoints.

Adds an `include` query parameter pattern that lets callers request child
entities in a single API call instead of making one call per level.

The main hierarchy (departments → classes → professors/students) is fetched
in a single PostgREST nested select, using the FK constraints registered in
Supabase. Presentations and timeframes require separate passes:
  - presentations: custom enrichment logic (presenting_students join)
  - timeframes: polymorphic linked_id — no FK, cannot use PostgREST traversal

Supported includes per endpoint:
  GET /departments  → classes, professors, students, presentations, timeframes
  GET /classes      → professors, students, presentations, timeframes

If professors/students/presentations/timeframes are requested on /departments,
classes is automatically promoted (required intermediate level).
"""

from typing import cast
from uuid import UUID

from fastapi import HTTPException

from app.supabase_io import read
from app.supabase_io.client import supabase
from app.utils import force_uuid


VALID_INCLUDES = frozenset({"classes", "professors", "students", "presentations", "timeframes"})
DEPARTMENT_ALLOWS = frozenset({"classes", "professors", "students", "presentations", "timeframes"})
CLASS_ALLOWS = frozenset({"professors", "students", "presentations", "timeframes"})
# Any of these on /departments implicitly requires "classes"
CLASS_CHILDREN = frozenset({"professors", "students", "presentations", "timeframes"})


def parse_include(raw: str | None, allowed: frozenset[str]) -> frozenset[str]:
    """Parse and validate the include= query string.

    Returns a frozenset of token strings, or an empty frozenset if raw is None/empty.
    Raises HTTPException(422) for unrecognised or endpoint-disallowed tokens.
    """
    if not raw:
        return frozenset()
    tokens = frozenset(t.strip() for t in raw.split(",") if t.strip())
    invalid = tokens - VALID_INCLUDES
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid include value(s): {sorted(invalid)}. "
                f"Valid values: {sorted(VALID_INCLUDES)}"
            ),
        )
    not_allowed = tokens - allowed
    if not_allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Include value(s) not allowed for this endpoint: {sorted(not_allowed)}. "
                f"Allowed: {sorted(allowed)}"
            ),
        )
    return tokens


def build_department_select(includes: frozenset[str]) -> str:
    """Build the PostgREST select string for a departments query.

    Professors and students are embedded inside classes via FK traversal.
    Presentations and timeframes are handled in separate passes and are
    never included in this select string.
    """
    if "classes" not in includes:
        return "*"
    class_parts = ["*"]
    if "professors" in includes:
        class_parts.append("professors(*)")
    if "students" in includes:
        class_parts.append("students(*)")
    return f"*, classes({', '.join(class_parts)})"


def build_class_select(includes: frozenset[str]) -> str:
    """Build the PostgREST select string for a classes query."""
    parts = ["*"]
    if "professors" in includes:
        parts.append("professors(*)")
    if "students" in includes:
        parts.append("students(*)")
    return ", ".join(parts) if len(parts) > 1 else "*"


def _group_by(rows: list[dict[str, object]], key: str) -> dict[str, list[dict[str, object]]]:
    """Group a list of dicts by the string value of `key`."""
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        k = str(row.get(key, ""))
        groups.setdefault(k, []).append(row)
    return groups


def _extract_ids(rows: list[dict[str, object]], key: str = "id") -> list[UUID]:
    """Extract and parse UUIDs from a list of row dicts."""
    ids = []
    for row in rows:
        raw = row.get(key)
        if raw is not None:
            try:
                ids.append(force_uuid(raw))
            except (ValueError, AttributeError):
                pass
    return ids


def _attach_timeframes(
    professors_by_class: dict[str, list[dict[str, object]]],
    students_by_class: dict[str, list[dict[str, object]]],
) -> None:
    """Batch-fetch timeframes and attach to professor/student records in-place."""
    linked_ids: list[UUID] = []
    for prof_list in professors_by_class.values():
        linked_ids.extend(_extract_ids(prof_list))
    for student_list in students_by_class.values():
        linked_ids.extend(_extract_ids(student_list))

    timeframes_by_id: dict[str, list[dict[str, object]]] = {}
    if linked_ids:
        tf_resp = read.get_timeframes(linked_id=linked_ids)
        for tf in cast(list[dict[str, object]], tf_resp.data or []):
            key = str(tf.get("linked_id", ""))
            timeframes_by_id.setdefault(key, []).append(tf)

    for prof_list in professors_by_class.values():
        for prof in prof_list:
            prof["timeframes"] = timeframes_by_id.get(str(prof.get("id", "")), [])
    for student_list in students_by_class.values():
        for student in student_list:
            student["timeframes"] = timeframes_by_id.get(str(student.get("id", "")), [])


def get_departments_nested(
    symposium_id: UUID | None,
    includes: frozenset[str],
) -> list[dict[str, object]]:
    """Fetch departments with optionally nested child data.

    Uses a single PostgREST nested select to pull departments → classes →
    professors/students in one DB round trip. Presentations and timeframes
    each require one additional pass (separate DB queries).
    """
    select_str = build_department_select(includes)
    query = supabase.table("departments").select(select_str)
    if symposium_id is not None:
        query = query.eq("symposium_id", str(symposium_id))
    resp = query.execute()
    departments = list(cast(list[dict[str, object]], resp.data or []))

    if "classes" not in includes or not departments:
        return departments

    # Flatten all embedded class records for the subsequent passes
    all_classes: list[dict[str, object]] = [
        cls
        for dept in departments
        for cls in cast(list[dict[str, object]], dept.get("classes", []))
    ]
    class_ids = _extract_ids(all_classes)

    if "presentations" in includes and class_ids:
        # get_presentations() already enriches with presenting_students
        pres_result = read.get_presentations(class_id=class_ids)
        presentations_by_class = _group_by(
            cast(list[dict[str, object]], pres_result.data or []), "class_id"
        )
        for cls in all_classes:
            cls["presentations"] = presentations_by_class.get(str(cls.get("id", "")), [])

    if "timeframes" in includes:
        professors_by_class: dict[str, list[dict[str, object]]] = {
            str(cls.get("id", "")): cast(list[dict[str, object]], cls.get("professors", []))
            for cls in all_classes
        }
        students_by_class: dict[str, list[dict[str, object]]] = {
            str(cls.get("id", "")): cast(list[dict[str, object]], cls.get("students", []))
            for cls in all_classes
        }
        _attach_timeframes(professors_by_class, students_by_class)

    return departments


def get_classes_nested(
    department_id: UUID | None,
    includes: frozenset[str],
) -> list[dict[str, object]]:
    """Fetch classes with optionally nested child data.

    Uses a single PostgREST nested select to pull classes → professors/students
    in one DB round trip. Presentations and timeframes each require one
    additional pass.
    """
    select_str = build_class_select(includes)
    query = supabase.table("classes").select(select_str)
    if department_id is not None:
        query = query.eq("department_id", str(department_id))
    resp = query.execute()
    classes = list(cast(list[dict[str, object]], resp.data or []))

    if not classes:
        return classes

    class_ids = _extract_ids(classes)

    if "presentations" in includes and class_ids:
        pres_result = read.get_presentations(class_id=class_ids)
        presentations_by_class = _group_by(
            cast(list[dict[str, object]], pres_result.data or []), "class_id"
        )
        for cls in classes:
            cls["presentations"] = presentations_by_class.get(str(cls.get("id", "")), [])

    if "timeframes" in includes:
        professors_by_class: dict[str, list[dict[str, object]]] = {
            str(cls.get("id", "")): cast(list[dict[str, object]], cls.get("professors", []))
            for cls in classes
        }
        students_by_class: dict[str, list[dict[str, object]]] = {
            str(cls.get("id", "")): cast(list[dict[str, object]], cls.get("students", []))
            for cls in classes
        }
        _attach_timeframes(professors_by_class, students_by_class)

    return classes
