"""Symposium CRUD + read endpoints."""
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from postgrest.base_request_builder import APIResponse

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.routers.events_helpers import (
    _serialize_update_fields,
    _normalize_counts,
    _sum_counts,
)
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase
from app.utils import rows_affected as _rows_affected

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/add_symposium")
def add_symposium(
    payload: request_schemas.AddSymposiumRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | UUID | list[UUID] | dict[str, int]]:
    """Create a new symposium with timeframes."""
    try:
        logger.info("add_symposium: name=%s  rooms=%s  timeframes=%d", payload.symposium_name, payload.rooms_available, len(payload.timeframes))
        symposium_id = uuid4()
        symposium = supabase_schemas.Symposium(
            id=symposium_id,
            name=payload.symposium_name,
            created_at=datetime.now(timezone.utc),
            rooms_available=payload.rooms_available,
            room_names=payload.room_names,
            default_buffer=payload.default_buffer,
        )
        symposium_insert_resp = write.insert("symposiums", [symposium.model_dump()])
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
        logger.warning("add_symposium validation error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("add_symposium failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_symposium")
def update_symposium(
    payload: request_schemas.UpdateSymposiumRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        logger.info("update_symposium: symposium_id=%s", payload.symposium_id)
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"symposium_id", "timeframes"},
        )
        updates["room_names"] = payload.room_names
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
        logger.exception("update_symposium failed: symposium_id=%s", payload.symposium_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to update symposium: {exc}"
        ) from exc


@router.delete("/delete_symposium")
def delete_symposium(
    symposium_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | dict[str, int]]:
    try:
        logger.info("delete_symposium: symposium_id=%s", symposium_id)
        counts = _normalize_counts(
            delete.delete_symposium(symposium_id), {"symposiums": 1}
        )
        logger.info("delete_symposium complete: counts=%s", counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_symposium failed: symposium_id=%s", symposium_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete symposium: {exc}"
        ) from exc


@router.get("/symposiums")
def get_symposiums(
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student", "attendee"])),
) -> APIResponse:
    try:
        return read.get_symposiums()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_symposiums failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/symposiums/{symposium_id}")
def get_symposium(
    symposium_id: UUID,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "attendee"])),
) -> dict[str, object]:
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
        logger.exception("get_symposium failed: symposium_id=%s", symposium_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposium: {exc}"
        ) from exc
