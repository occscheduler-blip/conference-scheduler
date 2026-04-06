from datetime import datetime, timedelta, timezone, date
from types import SimpleNamespace
from typing import Any
from uuid import uuid4, UUID
from postgrest.base_request_builder import APIResponse

from fastapi import APIRouter, Depends, HTTPException
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.utils import rows_affected as _rows_affected
from app.supabase_io import delete, read, write
from app.supabase_io.nested_read import (
    CLASS_CHILDREN,
    CLASS_ALLOWS,
    DEPARTMENT_ALLOWS,
    get_classes_nested,
    get_departments_nested,
    parse_include,
)
from app.supabase_io.client import supabase

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas
from app.scheduler import build_schedule_for_symposium

router = APIRouter(prefix="/events", tags=["events"])


def _serialize_update_fields(fields: dict[str, object]) -> dict[str, Any]:
    """
    Convert a dict of model fields into a JSON-serializable form for Supabase updates by
    converting all UUID values to strings.
    """
    serialized: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, UUID):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def _normalize_counts(
    counts: dict[str, int] | None, fallback: dict[str, int]
) -> dict[str, int]:
    if not isinstance(counts, dict):
        return dict(fallback)

    normalized: dict[str, int] = {}
    for key, value in counts.items():
        if isinstance(value, int) and value >= 0:
            normalized[key] = value

    if not normalized:
        return dict(fallback)

    return normalized


def _sum_counts(*groups: dict[str, int]) -> int:
    total = 0
    for group in groups:
        for value in group.values():
            if isinstance(value, int) and value >= 0:
                total += value
    return total


# Admin Only


@router.post("/add_symposium")
def add_symposium(
    payload: request_schemas.AddSymposiumRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    """Create a new symposium with timeframes.

    Args:
        payload (schemas.AddSymposiumRequest): symposium request payload.

    Returns:
        dict[str, Any]: status payload with inserted record counts.
    """
    try:
        symposium_id = uuid4()
        symposium = supabase_schemas.Symposium(
            id=symposium_id,
            name=payload.symposium_name,
            created_at=datetime.now(timezone.utc),
            rooms_available=payload.rooms_available,
            default_buffer=payload.default_buffer
        )
        symposium_payload = symposium.model_dump()
        symposium_insert_resp = write.insert("symposiums", [symposium_payload])
        symposiums_inserted = _rows_affected(symposium_insert_resp, fallback=1)

        timeframes = [
            supabase_schemas.Timeframe(
                id=uuid4(),
                linked_id=symposium_id,
                start_time=timeframe.start_time,
                end_time=timeframe.end_time,
            )
            for timeframe in payload.timeframes
        ]
        timeframe_payloads = [item.model_dump() for item in timeframes]
        timeframe_response = write.insert("timeframes", timeframe_payloads)
        timeframes_inserted = _rows_affected(
            timeframe_response, fallback=len(timeframes)
        )
        records_inserted = {
            "symposiums": symposiums_inserted,
            "timeframes": timeframes_inserted,
        }

        return {
            "status": "created",
            "symposium_id": symposium_id,
            "name": payload.symposium_name,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_department")
def add_department(
    payload: request_schemas.AddDepartmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    try:
        department = supabase_schemas.Department(
            id=uuid4(),
            department_name=payload.department_name,
            department_head_name=payload.department_head_name,
            email=payload.email,
            symposium_id=payload.symposium_id,
        )

        resp = write.insert("departments", [department.model_dump()])
        departments_inserted = _rows_affected(resp, fallback=1)
        records_inserted = {"departments": departments_inserted}

        return {
            "status": "Inserted",
            "department_id": department.id,
            "symposium_id": department.symposium_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_symposium")
def update_symposium(
    payload: request_schemas.UpdateSymposiumRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"symposium_id", "timeframes"},
        )
        if "symposium_name" in updates:
            updates["name"] = updates.pop("symposium_name")
        update_payload = _serialize_update_fields(updates)
        update_resp = (
            supabase.table("symposiums")
            .update(update_payload)
            .eq("id", str(payload.symposium_id))
            .execute()
        )
        records_updated = {
            "symposiums": _rows_affected(
                update_resp, fallback=1 if update_payload else 0
            )
        }

        deleted_timeframes = delete.delete_timeframes(payload.symposium_id)
        timeframes = [
            supabase_schemas.Timeframe(
                id=uuid4(),
                linked_id=payload.symposium_id,
                start_time=timeframe.start_time,
                end_time=timeframe.end_time,
            )
            for timeframe in payload.timeframes
        ]
        timeframe_payloads = [item.model_dump() for item in timeframes]
        timeframe_response = write.insert("timeframes", timeframe_payloads)
        timeframes_inserted = _rows_affected(
            timeframe_response, fallback=len(timeframes)
        )
        records_deleted = {"timeframes": deleted_timeframes}
        records_inserted = {"timeframes": timeframes_inserted}

        return {
            "status": "updated",
            "symposium_id": str(payload.symposium_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "records_deleted": records_deleted,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(
                records_updated, records_deleted, records_inserted
            ),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update symposium: {exc}"
        ) from exc


@router.delete("/delete_symposium")
def delete_symposium(
    symposium_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        counts = _normalize_counts(
            delete.delete_symposium(symposium_id), {"symposiums": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete symposium: {exc}"
        ) from exc


@router.delete("/delete_department")
def delete_department(
    department_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        counts = _normalize_counts(
            delete.delete_department(department_id), {"departments": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete department: {exc}"
        ) from exc


# Admins and Department Heads


@router.post("/add_class")
def add_class(
    payload: request_schemas.AddClassRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    try:
        class_id = uuid4()
        class_def = supabase_schemas.Class(
            id=class_id, name=payload.name, department_id=payload.department_id
        )
        class_resp = write.insert("classes", [class_def.model_dump()])
        professors = [
            supabase_schemas.Professor(
                id=uuid4(),
                name=professor.name,
                email=professor.email,
                class_id=class_id,
            )
            for professor in payload.professors
        ]
        professors_payload = [professor.model_dump() for professor in professors]
        prof_resp = write.insert("professors", professors_payload)
        class_inserted = _rows_affected(class_resp, fallback=1)
        professors_inserted = _rows_affected(
            prof_resp, fallback=len(professors_payload)
        )
        records_inserted = {
            "classes": class_inserted,
            "professors": professors_inserted,
        }
        return {
            "status": "Inserted",
            "class_id": class_def.id,
            "professor_ids": [professor.id for professor in professors],
            "department_id": class_def.department_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_department")
def update_department(
    payload: request_schemas.UpdateDepartmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        update_payload = {
            "department_name": payload.department_name,
            "department_head_name": payload.department_head_name,
            "email": payload.email,
        }
        update_resp = (
            supabase.table("departments")
            .update(update_payload)
            .eq("id", str(payload.department_id))
            .execute()
        )
        records_updated = {
            "departments": _rows_affected(
                update_resp, fallback=1 if update_payload else 0
            )
        }

        return {
            "status": "updated",
            "department_id": str(payload.department_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update department: {exc}"
        ) from exc


@router.delete("/delete_professor")
def delete_professor(
    professor_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        counts = _normalize_counts(
            delete.delete_professor(professor_id), {"professors": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete professor: {exc}"
        ) from exc


@router.delete("/delete_class")
def delete_class(
    class_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        counts = _normalize_counts(delete.delete_class(class_id), {"classes": 1})
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete class: {exc}"
        ) from exc


# Admins, Department Heads, and Professors


@router.post("/add_students")
def add_students(
    payload: request_schemas.AddStudentsRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    """Adds a list of students to the students table in the database."""
    try:
        students: list[supabase_schemas.Student] = []
        for student in payload.students:
            students.append(
                supabase_schemas.Student(
                    id=uuid4(),
                    name=student.name,
                    email=student.email,
                    class_id=payload.class_id,
                    presentation_id=None,
                )
            )

        students_payload = [item.model_dump() for item in students]
        response = write.insert("students", students_payload)
        students_inserted = _rows_affected(response, fallback=len(students_payload))
        records_inserted = {"students": students_inserted}
        return {
            "status": "inserted",
            "class_id": str(payload.class_id),
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_presentation")
def add_presentation(
    payload: request_schemas.AddPresentationRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | UUID | dict[str, int]]:
    try:
        presentation_id = uuid4()
        presentation_payload: dict[str, str | int | UUID | datetime | date | None] = {
            "id": presentation_id,
            "title": payload.title,
            "class_id": payload.class_id,
            "minutes": payload.minutes,
            "buffer": payload.buffer,
        }
        pres_resp = write.insert("presentations", [presentation_payload])

        students: list[supabase_schemas.PresentingStudents] = []
        for student in payload.presenting_students:
            students.append(
                supabase_schemas.PresentingStudents(
                    id=uuid4(), presentation_id=presentation_id, student_id=student
                )
            )
        students_payload = [item.model_dump() for item in students]
        students_resp = (
            write.insert("presenting_students", students_payload)
            if students_payload
            else None
        )

        presentations_inserted = _rows_affected(pres_resp, fallback=1)
        presenting_students_inserted = _rows_affected(
            students_resp, fallback=len(students_payload)
        )

        records_inserted = {
            "presentations": presentations_inserted,
            "presenting_students": presenting_students_inserted,
        }

        return {
            "status": "inserted",
            "presentation_id": presentation_id,
            "class_id": payload.class_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/schedule")
def run_schedule(
    body: request_schemas.RunSchedulerRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    try:
        result = build_schedule_for_symposium(body.symposium_id, slot_minutes=1)

        return {
            "status": result.status,
            "assignments": [
                {
                    "presentation_id": a.presentation_id,
                    "room_index": a.room_index,
                    "start": a.start.isoformat(),
                    "end": a.end.isoformat(),
                }
                for a in result.assignments
            ],
            "unscheduled_presentations": list(result.unscheduled_presentations),
            "diagnostics": list(result.diagnostics),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to run scheduler: {exc}"
        ) from exc
    

@router.put("/update_class")
def update_class(
    payload: request_schemas.UpdateClassRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"class_id"},
        )
        update_payload = _serialize_update_fields(updates)
        update_resp = (
            supabase.table("classes")
            .update(update_payload)
            .eq("id", str(payload.class_id))
            .execute()
        )
        records_updated = {
            "classes": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        return {
            "status": "updated",
            "class_id": str(payload.class_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update class: {exc}"
        ) from exc


@router.delete("/delete_presentation")
def delete_presentation(
    presentation_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        counts = _normalize_counts(
            delete.delete_presentation(presentation_id), {"presentations": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete presentation: {exc}"
        ) from exc


@router.delete("/delete_student")
def delete_student(
    student_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        counts = _normalize_counts(delete.delete_student(student_id), {"students": 1})
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to delete student: {exc}"
        ) from exc


# Admins, Department Heads, Professors, and Students


@router.put("/update_student")
def update_student(
    payload: request_schemas.UpdateStudentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"student_id"},
        )
        update_payload = _serialize_update_fields(updates)
        update_resp = (
            supabase.table("students")
            .update(update_payload)
            .eq("id", str(payload.student_id))
            .execute()
        )
        records_updated = {
            "students": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        return {
            "status": "updated",
            "student_id": str(payload.student_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update student: {exc}"
        ) from exc


@router.put("/update_professor")
def update_professor(
    payload: request_schemas.UpdateProfessorRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"professor_id"},
        )
        update_payload = _serialize_update_fields(updates)
        update_resp = (
            supabase.table("professors")
            .update(update_payload)
            .eq("id", str(payload.professor_id))
            .execute()
        )
        records_updated = {
            "professors": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        return {
            "status": "updated",
            "professor_id": str(payload.professor_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update professor: {exc}"
        ) from exc


@router.post("/add_request")
def add_request(
    payload: request_schemas.AddReqRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        request = supabase_schemas.Request(
            id=uuid4(),
            name=payload.name,
            email=payload.email,
            student_id=payload.student_id,
        )

        response = write.insert("requests", [request.model_dump()])
        prof_requests_inserted = _rows_affected(response, fallback=1)
        records_inserted = {"prof_requests": prof_requests_inserted}

        return {
            "status": "inserted",
            "name": payload.name,
            "email": payload.email,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_schedule_assignment")
def update_schedule_assignment(
    payload: request_schemas.UpdateScheduleAssignmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int]:
    """Atomically update a presentation's room and time slot with conflict detection."""
    try:
        symposium_id = str(payload.symposium_id)
        presentation_id = str(payload.presentation_id)

        # Fetch all departments -> classes -> presentations for this symposium
        departments_resp = read.get_departments(symposium_id=payload.symposium_id)
        departments = list(getattr(departments_resp, "data", None) or [])
        department_ids = [UUID(str(d["id"])) for d in departments if d.get("id")]

        all_classes: list[dict[str, Any]] = []
        if department_ids:
            classes_resp = read.get_classes(department_id=department_ids)
            all_classes = list(getattr(classes_resp, "data", None) or [])
        class_ids = [UUID(str(c["id"])) for c in all_classes if c.get("id")]

        all_presentations: list[dict[str, Any]] = []
        all_professors: list[dict[str, Any]] = []
        if class_ids:
            pres_resp = read.get_presentations(class_id=class_ids)
            all_presentations = list(getattr(pres_resp, "data", None) or [])
            prof_resp = read.get_professors(class_id=class_ids)
            all_professors = list(getattr(prof_resp, "data", None) or [])

        # Build professor lookup by class and name lookup by ID
        professors_by_class: dict[str, list[str]] = {}
        person_name_by_id: dict[str, str] = {}
        for prof in all_professors:
            cid = str(prof.get("class_id", ""))
            pid = str(prof.get("id", ""))
            if cid and pid:
                professors_by_class.setdefault(cid, []).append(pid)
                name = str(prof.get("name", "")).strip()
                if name:
                    person_name_by_id[pid] = name

        # Build resource set for the target presentation
        target_pres = None
        for p in all_presentations:
            if str(p.get("id", "")) == presentation_id:
                target_pres = p
                break
        if target_pres is None:
            raise HTTPException(status_code=404, detail="Presentation not found in this symposium.")

        target_class_id = str(target_pres.get("class_id", ""))
        target_resources: set[str] = set(professors_by_class.get(target_class_id, []))
        for s in target_pres.get("presenting_students", []):
            sid = str(s.get("id", s.get("student_id", "")))
            if sid:
                target_resources.add(sid)
                name = str(s.get("name", "")).strip()
                if name:
                    person_name_by_id[sid] = name

        new_start = payload.start_time if payload.start_time.tzinfo else payload.start_time.replace(tzinfo=timezone.utc)
        new_end = payload.end_time if payload.end_time.tzinfo else payload.end_time.replace(tzinfo=timezone.utc)
        target_buffer = timedelta(minutes=int(target_pres.get("buffer") or 0))
        new_buffered_end = new_end + target_buffer

        # Check conflicts against every other scheduled presentation
        other_pres_ids = [
            str(p["id"]) for p in all_presentations
            if str(p.get("id", "")) != presentation_id and p.get("id")
        ]

        if other_pres_ids:
            tf_resp = read.get_timeframes(
                linked_id=[UUID(pid) for pid in other_pres_ids]
            )
            other_timeframes = list(getattr(tf_resp, "data", None) or [])

            tf_by_pres: dict[str, dict[str, Any]] = {}
            for tf in other_timeframes:
                linked = str(tf.get("linked_id", ""))
                if linked:
                    tf_by_pres[linked] = tf

            for other in all_presentations:
                other_id = str(other.get("id", ""))
                if other_id == presentation_id or other_id not in tf_by_pres:
                    continue

                other_tf = tf_by_pres[other_id]
                other_start_raw = datetime.fromisoformat(
                    str(other_tf["start_time"]).replace("Z", "+00:00")
                )
                other_end_raw = datetime.fromisoformat(
                    str(other_tf["end_time"]).replace("Z", "+00:00")
                )
                other_start = other_start_raw if other_start_raw.tzinfo else other_start_raw.replace(tzinfo=timezone.utc)
                other_end = other_end_raw if other_end_raw.tzinfo else other_end_raw.replace(tzinfo=timezone.utc)
                other_buffer = timedelta(minutes=int(other.get("buffer") or 0))
                other_buffered_end = other_end + other_buffer
                times_overlap = new_start < other_buffered_end and new_buffered_end > other_start

                if not times_overlap:
                    continue

                other_room = other.get("room")
                # Room conflict
                if other_room is not None and int(other_room) == payload.room:
                    other_title = other.get("title", other_id)
                    raise HTTPException(
                        status_code=409,
                        detail=f"Room conflict: Room {payload.room + 1} is already occupied by \"{other_title}\" at that time.",
                    )

                # Person conflict (professor or presenting student)
                other_class_id = str(other.get("class_id", ""))
                other_resources: set[str] = set(professors_by_class.get(other_class_id, []))
                for s in other.get("presenting_students", []):
                    sid = str(s.get("id", s.get("student_id", "")))
                    if sid:
                        other_resources.add(sid)
                        name = str(s.get("name", "")).strip()
                        if name:
                            person_name_by_id[sid] = name

                shared = target_resources & other_resources
                if shared:
                    other_title = other.get("title", other_id)
                    conflicting_name = person_name_by_id.get(next(iter(shared)), "Someone")
                    is_professor = next(iter(shared)) in {
                        pid for profs in professors_by_class.values() for pid in profs
                    }
                    role = "Professor" if is_professor else "Student"
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Scheduling conflict: {role} \"{conflicting_name}\" is required at both "
                            f"this presentation and \"{other_title}\" at that time. "
                            f"They cannot be in two rooms at once."
                        ),
                    )

        # No conflicts — save the assignment
        supabase.table("presentations").update(
            {"room": payload.room}
        ).eq("id", presentation_id).execute()

        delete.delete_timeframes(payload.presentation_id)

        tf_row = supabase_schemas.Timeframe(
            id=uuid4(),
            linked_id=payload.presentation_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        write.insert("timeframes", [tf_row.model_dump()])

        return {
            "status": "updated",
            "presentation_id": presentation_id,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to update schedule assignment: {exc}"
        ) from exc


@router.put("/bulk_update_schedule_assignments")
def bulk_update_schedule_assignments(
    payload: request_schemas.BulkUpdateScheduleAssignmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    """Batch-update multiple presentation room/time assignments with conflict detection."""
    try:
        symposium_id = str(payload.symposium_id)
        assignment_map: dict[str, request_schemas.SingleScheduleAssignment] = {
            str(a.presentation_id): a for a in payload.assignments
        }

        # Fetch all departments -> classes -> presentations + professors
        departments_resp = read.get_departments(symposium_id=payload.symposium_id)
        departments = list(getattr(departments_resp, "data", None) or [])
        department_ids = [UUID(str(d["id"])) for d in departments if d.get("id")]

        all_classes: list[dict[str, Any]] = []
        if department_ids:
            classes_resp = read.get_classes(department_id=department_ids)
            all_classes = list(getattr(classes_resp, "data", None) or [])
        class_ids = [UUID(str(c["id"])) for c in all_classes if c.get("id")]

        all_presentations: list[dict[str, Any]] = []
        all_professors: list[dict[str, Any]] = []
        if class_ids:
            pres_resp = read.get_presentations(class_id=class_ids)
            all_presentations = list(getattr(pres_resp, "data", None) or [])
            prof_resp = read.get_professors(class_id=class_ids)
            all_professors = list(getattr(prof_resp, "data", None) or [])

        # Build professor lookup by class and name lookup by ID
        professors_by_class: dict[str, list[str]] = {}
        person_name_by_id: dict[str, str] = {}
        for prof in all_professors:
            cid = str(prof.get("class_id", ""))
            pid = str(prof.get("id", ""))
            if cid and pid:
                professors_by_class.setdefault(cid, []).append(pid)
                name = str(prof.get("name", "")).strip()
                if name:
                    person_name_by_id[pid] = name

        # Validate all target presentations exist
        pres_by_id: dict[str, dict[str, Any]] = {
            str(p["id"]): p for p in all_presentations if p.get("id")
        }
        for pid in assignment_map:
            if pid not in pres_by_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Presentation {pid} not found in this symposium.",
                )

        # Build resource sets for each presentation
        def _resources_for(pres: dict[str, Any]) -> set[str]:
            cid = str(pres.get("class_id", ""))
            resources: set[str] = set(professors_by_class.get(cid, []))
            for s in pres.get("presenting_students", []):
                sid = str(s.get("id", s.get("student_id", "")))
                if sid:
                    resources.add(sid)
                    name = str(s.get("name", "")).strip()
                    if name:
                        person_name_by_id[sid] = name
            return resources

        # Build the effective schedule: for each presentation, use the batch
        # assignment if present, otherwise use the existing DB timeframe/room.
        # A presentation is "scheduled" if it has both a room and a timeframe.
        # Tuple: (room, start, buffered_end) where buffered_end = end + buffer
        EffSlot = tuple[int, datetime, datetime]  # (room, start, buffered_end)
        effective: dict[str, EffSlot] = {}

        # First, load existing timeframes for all non-batch presentations
        non_batch_ids = [
            UUID(str(p["id"])) for p in all_presentations
            if str(p.get("id", "")) not in assignment_map and p.get("id")
        ]
        existing_tf: dict[str, dict[str, Any]] = {}
        if non_batch_ids:
            tf_resp = read.get_timeframes(linked_id=non_batch_ids)
            for tf in list(getattr(tf_resp, "data", None) or []):
                linked = str(tf.get("linked_id", ""))
                if linked:
                    existing_tf[linked] = tf

        for p in all_presentations:
            pid = str(p.get("id", ""))
            buf = timedelta(minutes=int(p.get("buffer") or 0))
            if pid in assignment_map:
                a = assignment_map[pid]
                start = a.start_time if a.start_time.tzinfo else a.start_time.replace(tzinfo=timezone.utc)
                end = a.end_time if a.end_time.tzinfo else a.end_time.replace(tzinfo=timezone.utc)
                effective[pid] = (a.room, start, end + buf)
            elif pid in existing_tf:
                room_val = p.get("room")
                if room_val is None:
                    continue
                tf = existing_tf[pid]
                start_raw = datetime.fromisoformat(str(tf["start_time"]).replace("Z", "+00:00"))
                end_raw = datetime.fromisoformat(str(tf["end_time"]).replace("Z", "+00:00"))
                start = start_raw if start_raw.tzinfo else start_raw.replace(tzinfo=timezone.utc)
                end = end_raw if end_raw.tzinfo else end_raw.replace(tzinfo=timezone.utc)
                effective[pid] = (int(room_val), start, end + buf)

        # Check all pairs for conflicts
        scheduled_ids = list(effective.keys())
        for i, pid_a in enumerate(scheduled_ids):
            room_a, start_a, buffered_end_a = effective[pid_a]
            pres_a = pres_by_id.get(pid_a, {})
            resources_a = _resources_for(pres_a)

            for pid_b in scheduled_ids[i + 1:]:
                room_b, start_b, buffered_end_b = effective[pid_b]
                times_overlap = start_a < buffered_end_b and buffered_end_a > start_b
                if not times_overlap:
                    continue

                # Only report conflicts involving at least one batch assignment
                if pid_a not in assignment_map and pid_b not in assignment_map:
                    continue

                pres_b = pres_by_id.get(pid_b, {})

                # Room conflict
                if room_a == room_b:
                    title_a = pres_a.get("title", pid_a)
                    title_b = pres_b.get("title", pid_b)
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Room conflict: Room {room_a + 1} is double-booked between "
                            f"\"{title_a}\" and \"{title_b}\" at that time."
                        ),
                    )

                # Person conflict
                resources_b = _resources_for(pres_b)
                shared = resources_a & resources_b
                if shared:
                    title_a = pres_a.get("title", pid_a)
                    title_b = pres_b.get("title", pid_b)
                    conflicting_name = person_name_by_id.get(next(iter(shared)), "Someone")
                    is_professor = next(iter(shared)) in {
                        pid for profs in professors_by_class.values() for pid in profs
                    }
                    role = "Professor" if is_professor else "Student"
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Scheduling conflict: {role} \"{conflicting_name}\" is required at both "
                            f"\"{title_a}\" and \"{title_b}\" at that time. "
                            f"They cannot be in two rooms at once."
                        ),
                    )

        # No conflicts — save all assignments
        batch_pids = [UUID(pid) for pid in assignment_map]
        delete.delete_timeframes(batch_pids)

        tf_rows: list[dict[str, str | int | UUID | datetime | date | None]] = []
        for pid, a in assignment_map.items():
            supabase.table("presentations").update(
                {"room": a.room}
            ).eq("id", pid).execute()
            tf_rows.append({
                "id": uuid4(),
                "linked_id": UUID(pid),
                "start_time": a.start_time,
                "end_time": a.end_time,
            })

        if tf_rows:
            write.insert("timeframes", tf_rows)

        return {
            "status": "updated",
            "count": len(assignment_map),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to bulk update schedule assignments: {exc}"
        ) from exc


@router.put("/update_timeframes")
def update_timeframes(
    payload: request_schemas.UpdateTimeframesRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | UUID | dict[str, int]]:
    try:
        deleted_timeframes = delete.delete_timeframes(payload.linked_id)

        timeframes = [
            supabase_schemas.Timeframe(
                id=uuid4(),
                linked_id=payload.linked_id,
                start_time=timeframe.start_time,
                end_time=timeframe.end_time,
            )
            for timeframe in payload.timeframes
        ]
        timeframe_payload = [item.model_dump() for item in timeframes]
        timeframe_resp = write.insert("timeframes", timeframe_payload)
        timeframes_inserted = _rows_affected(
            timeframe_resp, fallback=len(timeframe_payload)
        )
        records_deleted = {"timeframes": deleted_timeframes}
        records_inserted = {"timeframes": timeframes_inserted}

        return {
            "status": "updated",
            "linked_id": payload.linked_id,
            "records_deleted": records_deleted,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_deleted, records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to update timeframes: {exc}"
        ) from exc


@router.put("/update_presentation")
def update_presentation(
    payload: request_schemas.UpdatePresentationRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | bool | list[str] | dict[str, int]]:
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"presentation_id", "presenting_students"},
        )
        update_payload = _serialize_update_fields(updates)
        presentations_updated = 0
        presenting_students_deleted = 0
        presenting_students_inserted = 0

        if update_payload:
            presentation_update_resp = (
                supabase.table("presentations")
                .update(update_payload)
                .eq("id", str(payload.presentation_id))
                .execute()
            )
            presentations_updated = _rows_affected(presentation_update_resp)

        if payload.presenting_students is not None:
            presenting_students_delete_resp = (
                supabase.table("presenting_students")
                .delete()
                .eq("presentation_id", str(payload.presentation_id))
                .execute()
            )
            presenting_students_deleted = _rows_affected(
                presenting_students_delete_resp
            )
            presenting_students_payload = [
                supabase_schemas.PresentingStudents(
                    id=uuid4(),
                    presentation_id=payload.presentation_id,
                    student_id=student_id,
                ).model_dump()
                for student_id in payload.presenting_students
            ]
            if presenting_students_payload:
                presenting_students_insert_resp = write.insert(
                    "presenting_students", presenting_students_payload
                )
                presenting_students_inserted = _rows_affected(
                    presenting_students_insert_resp,
                    fallback=len(presenting_students_payload),
                )

        records_inserted = {"presenting_students": presenting_students_inserted}
        records_deleted = {"presenting_students": presenting_students_deleted}
        records_updated = {"presentations": presentations_updated}

        return {
            "status": "updated",
            "presentation_id": str(payload.presentation_id),
            "fields_updated": sorted(update_payload.keys()),
            "presenting_students_updated": payload.presenting_students is not None,
            "records_inserted": records_inserted,
            "records_deleted": records_deleted,
            "records_updated": records_updated,
            "lines_edited": _sum_counts(
                records_inserted, records_deleted, records_updated
            ),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update presentation: {exc}"
        ) from exc


# Undecided/Not Sure


@router.get("/symposiums")
def get_symposiums() -> APIResponse:
    try:
        return read.get_symposiums()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/symposiums/{symposium_id}")
def get_symposium(symposium_id: UUID) -> dict[str, object]:
    try:
        symposium_response = (
            supabase.table("symposiums")
            .select("*")
            .eq("id", str(symposium_id))
            .limit(1)
            .execute()
        )
        symposium_rows = list(getattr(symposium_response, "data", None) or [])
        if not symposium_rows:
            raise HTTPException(status_code=404, detail="Symposium not found.")

        timeframe_response = read.get_timeframes(linked_id=symposium_id)
        timeframe_rows = list(getattr(timeframe_response, "data", None) or [])
        return {
            "symposium": symposium_rows[0],
            "timeframes": timeframe_rows,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposium: {exc}"
        ) from exc


@router.get("/departments", response_model=None)
def get_departments(
    symposium_id: UUID | None = None,
    include: str | None = None,
) -> APIResponse | list[dict[str, object]]:
    try:
        includes = parse_include(include, allowed=DEPARTMENT_ALLOWS)
        if includes:
            if includes & CLASS_CHILDREN:
                includes = includes | {"classes"}
            return get_departments_nested(symposium_id=symposium_id, includes=includes)
        return read.get_departments(symposium_id=symposium_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get departments: {exc}"
        ) from exc


@router.get("/classes", response_model=None)
def get_classes(
    department_id: UUID | None = None,
    include: str | None = None,
) -> APIResponse | list[dict[str, object]]:
    try:
        includes = parse_include(include, allowed=CLASS_ALLOWS)
        if includes:
            return get_classes_nested(department_id=department_id, includes=includes)
        return read.get_classes(department_id=department_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get classes: {exc}"
        ) from exc


@router.get("/students")
def get_students(class_id: UUID | None = None) -> APIResponse:
    try:
        return read.get_students(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get students: {exc}"
        ) from exc


@router.get("/presentations", response_model=None)
def get_presentations(class_id: UUID | None = None) -> SimpleNamespace | APIResponse:
    try:
        return read.get_presentations(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get presentations: {exc}"
        ) from exc


@router.get("/professors")
def get_professors(class_id: UUID | None = None) -> APIResponse:
    try:
        return read.get_professors(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get professors: {exc}"
        ) from exc


@router.get("/timeframes")
def get_timeframes(linked_id: UUID | None = None) -> APIResponse:
    try:
        return read.get_timeframes(linked_id=linked_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get timeframes: {exc}"
        ) from exc


@router.get("/requests")
def get_requests(student_id: UUID | None = None) -> APIResponse:
    try:
        return read.get_requests(student_id=student_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get requests: {exc}"
        ) from exc
