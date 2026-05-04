"""Presentation CRUD + read endpoints."""
import logging
from datetime import date, datetime
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


@router.post("/add_presentation")
def add_presentation(
    payload: request_schemas.AddPresentationRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | UUID | dict[str, int]]:
    try:
        logger.info("add_presentation: title=%s  class_id=%s  minutes=%d  students=%d", payload.title, payload.class_id, payload.minutes, len(payload.presenting_students))
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
        logger.warning("add_presentation validation error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("add_presentation failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_presentation")
def update_presentation(
    payload: request_schemas.UpdatePresentationRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | bool | list[str] | dict[str, int]]:
    try:
        logger.info("update_presentation: presentation_id=%s", payload.presentation_id)
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
        logger.exception("update_presentation failed: presentation_id=%s", payload.presentation_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to update presentation: {exc}"
        ) from exc


@router.delete("/delete_presentation")
def delete_presentation(
    presentation_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("delete_presentation: presentation_id=%s", presentation_id)
        counts = _normalize_counts(
            delete.delete_presentation(presentation_id), {"presentations": 1}
        )
        logger.info("delete_presentation complete: counts=%s", counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_presentation failed: presentation_id=%s", presentation_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete presentation: {exc}"
        ) from exc


@router.put("/update_presentation_buffers")
def update_presentation_buffers(
    payload: request_schemas.UpdateSymposiumBuffersRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    """Set every presentation buffer in a symposium to the given value in one shot."""
    try:
        logger.info("update_presentation_buffers: symposium_id=%s  buffer=%d", payload.symposium_id, payload.buffer_minutes)
        dept_resp = read.get_departments(symposium_id=payload.symposium_id)
        dept_ids = [row["id"] for row in (dept_resp.data or [])]
        if not dept_ids:
            return {"status": "ok", "presentations_updated": 0}

        class_resp = read.get_classes(department_id=[UUID(d) for d in dept_ids])
        class_ids = [str(row["id"]) for row in (class_resp.data or [])]
        if not class_ids:
            return {"status": "ok", "presentations_updated": 0}

        resp = (
            supabase.table("presentations")
            .update({"buffer": payload.buffer_minutes})
            .in_("class_id", class_ids)
            .execute()
        )
        count = len(resp.data) if resp.data else 0
        logger.info("update_presentation_buffers: updated %d presentations", count)
        return {"status": "ok", "presentations_updated": count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("update_presentation_buffers failed")
        raise HTTPException(status_code=500, detail=f"Failed to update buffers: {exc}") from exc


@router.get("/presentations", response_model=None)
def get_presentations(class_id: str | None = None) -> APIResponse:
    try:
        return read.get_presentations(class_id=_parse_uuid_list(class_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_presentations failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get presentations: {exc}"
        ) from exc
