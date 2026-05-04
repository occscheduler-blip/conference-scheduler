"""Department CRUD + read endpoints."""
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from postgrest.base_request_builder import APIResponse

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.routers.events_helpers import (
    _checked_update,
    _normalize_counts,
    _parse_uuid_list,
    _sum_counts,
)
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase
from app.supabase_io.locks import maybe_symposium_lock
from app.supabase_io.nested_read import (
    CLASS_CHILDREN,
    DEPARTMENT_ALLOWS,
    get_departments_nested,
    parse_include,
)
from app.utils import rows_affected as _rows_affected

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/add_department")
def add_department(
    payload: request_schemas.AddDepartmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    try:
        logger.info("add_department: name=%s  symposium_id=%s", payload.department_name, payload.symposium_id)
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
        logger.warning("add_department validation error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("add_department failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_department")
def update_department(
    payload: request_schemas.UpdateDepartmentRequest,
    claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        logger.info("update_department: department_id=%s", payload.department_id)
        update_payload = {
            "department_name": payload.department_name,
            "department_head_name": payload.department_head_name,
            "email": payload.email,
        }
        records_updated = {
            "departments": _checked_update(
                "departments",
                str(payload.department_id),
                update_payload,
                payload.expected_updated_at,
                actor_id=claims.sub,
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
        logger.exception("update_department failed: department_id=%s", payload.department_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to update department: {exc}"
        ) from exc


@router.delete("/delete_department")
def delete_department(
    department_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("delete_department: department_id=%s", department_id)
        sym_id = read.resolve_symposium_for_linked(department_id)
        with maybe_symposium_lock(sym_id):
            counts = _normalize_counts(
                delete.delete_department(department_id), {"departments": 1}
            )
        logger.info("delete_department complete: counts=%s", counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_department failed: department_id=%s", department_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete department: {exc}"
        ) from exc


@router.get("/departments", response_model=None)
def get_departments(
    symposium_id: str | None = None,
    include: str | None = None,
) -> APIResponse | list[dict[str, object]]:
    try:
        ids = _parse_uuid_list(symposium_id)
        includes = parse_include(include, allowed=DEPARTMENT_ALLOWS)
        if includes:
            if includes & CLASS_CHILDREN:
                includes = includes | {"classes"}
            return get_departments_nested(symposium_id=ids, includes=includes)
        return read.get_departments(symposium_id=ids)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_departments failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get departments: {exc}"
        ) from exc
