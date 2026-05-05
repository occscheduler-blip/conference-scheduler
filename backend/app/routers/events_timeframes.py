"""Timeframe endpoints (polymorphic — can be linked to symposium/professor/student)."""
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from postgrest.base_request_builder import APIResponse

import app.routers.request_schemas as request_schemas
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.routers.events_helpers import _parse_uuid_list, _sum_counts
from app.supabase_io import read
from app.supabase_io.locks import symposium_lock

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put("/update_timeframes")
def update_timeframes(
    payload: request_schemas.UpdateTimeframesRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor", "student"])),
) -> dict[str, str | int | UUID | dict[str, int]]:
    try:
        logger.info("update_timeframes: linked_id=%s  count=%d", payload.linked_id, len(payload.timeframes))

        symposium_id = read.resolve_symposium_for_linked(payload.linked_id)
        if symposium_id is None:
            raise HTTPException(
                status_code=404,
                detail="linked_id does not match any symposium / professor / student / presentation.",
            )

        # Hold the symposium lock and do delete+insert in a single psycopg
        # transaction so there is never an empty-availability window visible
        # to a concurrent reader (scheduler, other tab) and crash recovery
        # leaves the previous timeframes intact.
        with symposium_lock(symposium_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.timeframes WHERE linked_id = %s",
                    (str(payload.linked_id),),
                )
                deleted_timeframes = cur.rowcount or 0

                rows = [
                    (
                        str(uuid4()),
                        str(payload.linked_id),
                        tf.start_time,
                        tf.end_time,
                    )
                    for tf in payload.timeframes
                ]
                if rows:
                    cur.executemany(
                        "INSERT INTO public.timeframes (id, linked_id, start_time, end_time)"
                        " VALUES (%s, %s, %s, %s)",
                        rows,
                    )
                timeframes_inserted = len(rows)

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
def get_timeframes(linked_id: str | None = None) -> APIResponse:
    try:
        return read.get_timeframes(linked_id=_parse_uuid_list(linked_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_timeframes failed")
        raise HTTPException(
            status_code=400, detail=f"Failed to get timeframes: {exc}"
        ) from exc
