"""Timeframe endpoints (polymorphic — can be linked to symposium/professor/student)."""
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from postgrest.base_request_builder import APIResponse

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.routers.events_helpers import _parse_uuid_list, _sum_counts
from app.supabase_io import delete, read, write
from app.utils import rows_affected as _rows_affected

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put("/update_timeframes")
def update_timeframes(
    payload: request_schemas.UpdateTimeframesRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | UUID | dict[str, int]]:
    try:
        logger.info("update_timeframes: linked_id=%s  count=%d", payload.linked_id, len(payload.timeframes))
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
        logger.exception("update_timeframes failed: linked_id=%s", payload.linked_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to update timeframes: {exc}"
        ) from exc


@router.get("/timeframes")
def get_timeframes(
    linked_id: str | None = None,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "professor", "student", "attendee"])),
) -> APIResponse:
    try:
        return read.get_timeframes(linked_id=_parse_uuid_list(linked_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_timeframes failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get timeframes: {exc}"
        ) from exc
