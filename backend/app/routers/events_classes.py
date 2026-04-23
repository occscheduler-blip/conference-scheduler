"""Class CRUD + read endpoints."""
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
from app.supabase_io.nested_read import (
    CLASS_ALLOWS,
    get_classes_nested,
    parse_include,
)
from app.utils import rows_affected as _rows_affected

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/add_class")
def add_class(
    payload: request_schemas.AddClassRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    try:
        logger.info("add_class: name=%s  department_id=%s  professors=%d", payload.name, payload.department_id, len(payload.professors))
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
        logger.warning("add_class validation error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("add_class failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_class")
def update_class(
    payload: request_schemas.UpdateClassRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        logger.info("update_class: class_id=%s", payload.class_id)
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
        logger.exception("update_class failed: class_id=%s", payload.class_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to update class: {exc}"
        ) from exc


@router.delete("/delete_class")
def delete_class(
    class_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("delete_class: class_id=%s", class_id)
        counts = _normalize_counts(delete.delete_class(class_id), {"classes": 1})
        logger.info("delete_class complete: counts=%s", counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_class failed: class_id=%s", class_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete class: {exc}"
        ) from exc


@router.get("/classes", response_model=None)
def get_classes(
    department_id: str | None = None,
    include: str | None = None,
) -> APIResponse | list[dict[str, object]]:
    try:
        ids = _parse_uuid_list(department_id)
        includes = parse_include(include, allowed=CLASS_ALLOWS)
        if includes:
            return get_classes_nested(department_id=ids, includes=includes)
        return read.get_classes(department_id=ids)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_classes failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get classes: {exc}"
        ) from exc
