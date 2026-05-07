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
    _checked_update,
    _serialize_update_fields,
    _normalize_counts,
    _sum_counts,
)
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase
from app.supabase_io.locks import symposium_lock
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
    claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int | list[str] | dict[str, int]]:
    try:
        logger.info("update_symposium: symposium_id=%s", payload.symposium_id)
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"symposium_id", "timeframes", "expected_updated_at"},
        )
        updates["room_names"] = payload.room_names
        if "symposium_name" in updates:
            updates["name"] = updates.pop("symposium_name")
        update_payload = _serialize_update_fields(updates)

        # Hold the symposium lock so the symposium row update + timeframes
        # delete+insert are serialized vs. concurrent edits and the scheduler.
        with symposium_lock(payload.symposium_id) as conn:
            symposiums_updated = _checked_update(
                "symposiums",
                str(payload.symposium_id),
                update_payload,
                payload.expected_updated_at,
                actor_id=claims.sub,
            )
            records_updated = {"symposiums": symposiums_updated}

            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.timeframes WHERE linked_id = %s",
                    (str(payload.symposium_id),),
                )
                deleted_timeframes = cur.rowcount or 0

                rows = [
                    (
                        str(uuid4()),
                        str(payload.symposium_id),
                        timeframe.start_time,
                        timeframe.end_time,
                    )
                    for timeframe in payload.timeframes
                ]
                if rows:
                    cur.executemany(
                        "INSERT INTO public.timeframes (id, linked_id, start_time, end_time)"
                        " VALUES (%s, %s, %s, %s)",
                        rows,
                    )
                timeframes_inserted = len(rows)

                # Reducing rooms_available or shrinking/changing the symposium
                # timeframes leaves orphan draft assignments that no longer
                # fit. Unschedule them so the manual scheduler doesn't render
                # them into CSS Grid implicit columns past the rightmost room
                # or as blocks floating outside the day grid — the user can
                # re-place them from the Unscheduled panel.
                cur.execute(
                    """
                    SELECT p.id
                    FROM public.presentations p
                    JOIN public.classes c ON p.class_id = c.id
                    JOIN public.departments d ON c.department_id = d.id
                    LEFT JOIN public.temporary_timeframes tt ON tt.linked_id = p.id
                    WHERE d.symposium_id = %(sym_id)s
                      AND (
                        (p.temporary_room IS NOT NULL AND p.temporary_room >= %(rooms)s)
                        OR (
                          tt.id IS NOT NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM public.timeframes sym_tf
                            WHERE sym_tf.linked_id = %(sym_id)s
                              AND tt.start_time >= sym_tf.start_time
                              AND tt.end_time <= sym_tf.end_time
                          )
                        )
                      )
                    GROUP BY p.id
                    """,
                    {
                        "sym_id": str(payload.symposium_id),
                        "rooms": payload.rooms_available,
                    },
                )
                stale_presentation_ids = [row[0] for row in cur.fetchall()]
                if stale_presentation_ids:
                    cur.execute(
                        "UPDATE public.presentations SET temporary_room = NULL"
                        " WHERE id = ANY(%s)",
                        (stale_presentation_ids,),
                    )
                    presentations_unscheduled = cur.rowcount or 0
                    cur.execute(
                        "DELETE FROM public.temporary_timeframes"
                        " WHERE linked_id = ANY(%s)",
                        (stale_presentation_ids,),
                    )
                    deleted_temporary_timeframes = cur.rowcount or 0
                    logger.info(
                        "update_symposium: %s — unscheduled %d presentation(s) whose room or time no longer fits",
                        payload.symposium_id, presentations_unscheduled,
                    )
                else:
                    presentations_unscheduled = 0
                    deleted_temporary_timeframes = 0

        records_deleted = {
            "timeframes": deleted_timeframes,
            "temporary_timeframes": deleted_temporary_timeframes,
        }
        records_updated["presentations"] = presentations_unscheduled
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
        with symposium_lock(symposium_id):
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
def get_symposiums() -> APIResponse:
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
        logger.exception("get_symposium failed: symposium_id=%s", symposium_id)
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposium: {exc}"
        ) from exc
