"""Student / professor / request CRUD + read endpoints."""
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from postgrest.base_request_builder import APIResponse

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.routers.events_helpers import (
    _normalize_counts,
    _parse_uuid_list,
    _serialize_update_fields,
    _sum_counts,
)
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase
from app.utils import rows_affected as _rows_affected

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Students ──────────────────────────────────────────────────────────────

@router.post("/add_students")
def add_students(
    payload: request_schemas.AddStudentsRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    """Adds a list of students to the students table in the database."""
    try:
        logger.info("add_students: class_id=%s  count=%d", payload.class_id, len(payload.students))
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
        logger.warning("add_students validation error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("add_students failed: class_id=%s", payload.class_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_student")
def update_student(
    payload: request_schemas.UpdateStudentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        logger.info("update_student: student_id=%s", payload.student_id)
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
        logger.exception("update_student failed: student_id=%s", payload.student_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to update student: {exc}"
        ) from exc


@router.delete("/delete_student")
def delete_student(
    student_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("delete_student: student_id=%s", student_id)
        counts = _normalize_counts(delete.delete_student(student_id), {"students": 1})
        logger.info("delete_student complete: counts=%s", counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_student failed: student_id=%s", student_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete student: {exc}"
        ) from exc


@router.get("/students")
def get_students(class_id: str | None = None) -> APIResponse:
    try:
        return read.get_students(class_id=_parse_uuid_list(class_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_students failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get students: {exc}"
        ) from exc


# ── Professors ────────────────────────────────────────────────────────────

@router.put("/update_professor")
def update_professor(
    payload: request_schemas.UpdateProfessorRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        logger.info("update_professor: professor_id=%s", payload.professor_id)
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
        logger.exception("update_professor failed: professor_id=%s", payload.professor_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to update professor: {exc}"
        ) from exc


@router.delete("/delete_professor")
def delete_professor(
    professor_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("delete_professor: professor_id=%s", professor_id)
        counts = _normalize_counts(
            delete.delete_professor(professor_id), {"professors": 1}
        )
        logger.info("delete_professor complete: counts=%s", counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_professor failed: professor_id=%s", professor_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete professor: {exc}"
        ) from exc


@router.get("/professors")
def get_professors(class_id: str | None = None) -> APIResponse:
    try:
        return read.get_professors(class_id=_parse_uuid_list(class_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_professors failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get professors: {exc}"
        ) from exc


# ── Requests (students' professor preferences) ────────────────────────────

@router.post("/add_request")
def add_request(
    payload: request_schemas.AddReqRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("add_request: student_id=%s  name=%s", payload.student_id, payload.name)
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
        logger.warning("add_request validation error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("add_request failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.get("/requests")
def get_requests(student_id: str | None = None) -> APIResponse:
    try:
        return read.get_requests(student_id=_parse_uuid_list(student_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_requests failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get requests: {exc}"
        ) from exc
