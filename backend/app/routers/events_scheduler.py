"""Scheduler endpoints: run solver, check job status, publish, and manual edits."""
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from postgrest.base_request_builder import APIResponse

import app.routers.request_schemas as request_schemas
from app.auth.dependencies import require_jwt
from app.auth.jwt_utils import JWTClaims
from app.routers.events_helpers import (
    _assert_within_symposium_windows,
    _load_room_names,
    _parse_uuid_list,
    _room_label,
)
from app.scheduler import BuildScheduleForSymposium
from app.scheduler.conflicts import (
    BuildConflictIndex,
    FormatPersonConflictPair,
    FormatPersonConflictSingle,
    FormatRoomConflictPair,
    FormatRoomConflictSingle,
    LoadSymposiumEntities,
)
from app.scheduler.models import ScheduleConstraints
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase
from app.utils import ensure_app_timezone, parse_app_datetime

logger = logging.getLogger(__name__)
router = APIRouter()


def _RunScheduleJob(job_id: str, symposium_id: str, constraints: ScheduleConstraints, slot_minutes: int) -> None:
    """Background thread: run the solver and write results back to scheduler_jobs.

    Each thread gets its own supabase connection pool via the thread-local proxy
    in app.supabase_io.client, so there is no HTTP/2 stream-state sharing with
    the request-handler threads.
    """
    def _Update(payload: dict[str, Any]) -> None:
        try:
            supabase.table("scheduler_jobs").update({**payload, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", job_id).execute()
        except Exception:
            logger.exception("schedule job %s: failed to update status to %s", job_id, payload.get("status"))

    try:
        _Update({"status": "running"})
        result = BuildScheduleForSymposium(symposium_id, slot_minutes=slot_minutes, constraints=constraints)
        logger.info("schedule job %s complete: status=%s  assignments=%d", job_id, result.status, len(result.assignments))
        result_payload = {
            "status": result.status,
            "assignments": [
                {"presentation_id": a.presentation_id, "room_index": a.room_index, "start": a.start.isoformat(), "end": a.end.isoformat()}
                for a in result.assignments
            ],
            "unscheduled_presentations": list(result.unscheduled_presentations),
            "diagnostics": list(result.diagnostics),
        }
        _Update({"status": "completed", "result": result_payload})
    except Exception as exc:
        logger.exception("schedule job %s failed", job_id)
        _Update({"status": "failed", "error": str(exc)})


@router.post("/schedule")
def RunSchedule(
    body: request_schemas.RunSchedulerRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    try:
        logger.info("run_schedule: symposium_id=%s", body.symposium_id)
        constraints = ScheduleConstraints(
            room_conflicts=body.constraints.room_conflicts,
            person_conflicts=body.constraints.person_conflicts,
            symposium_windows=body.constraints.symposium_windows,
            professor_availability=body.constraints.professor_availability,
            student_availability=body.constraints.student_availability,
            same_class_same_room=body.constraints.same_class_same_room,
            slot_alignment=body.constraints.slot_alignment,
            minimize_makespan=body.constraints.minimize_makespan,
            minimize_class_span=body.constraints.minimize_class_span,
            minimize_professor_span=body.constraints.minimize_professor_span,
            balance_rooms=body.constraints.balance_rooms,
        )
        slot_minutes = max(1, body.constraints.slot_alignment)

        job_row = (
            supabase.table("scheduler_jobs")
            .insert({"symposium_id": str(body.symposium_id), "status": "pending"})
            .execute()
        )
        job_id = cast(dict[str, Any], job_row.data[0])["id"]

        thread = threading.Thread(target=_RunScheduleJob, args=(job_id, str(body.symposium_id), constraints, slot_minutes), daemon=True)
        thread.start()

        return {"job_id": job_id}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("run_schedule failed: symposium_id=%s", body.symposium_id)
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {exc}") from exc


@router.get("/schedule_job/{job_id}")
def GetScheduleJob(
    job_id: str,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    try:
        rows = supabase.table("scheduler_jobs").select("*").eq("id", job_id).execute()
        if not rows.data:
            raise HTTPException(status_code=404, detail="Job not found")
        job = cast(dict[str, Any], rows.data[0])
        return {
            "job_id": job["id"],
            "status": job["status"],
            "result": job.get("result"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_schedule_job failed: job_id=%s", job_id)
        raise HTTPException(status_code=500, detail=f"Failed to fetch job: {exc}") from exc


@router.get("/temporary_timeframes")
def GetTemporaryTimeframes(
    linked_id: str | None = None,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> APIResponse:
    try:
        return read.get_temporary_timeframes(linked_id=_parse_uuid_list(linked_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_temporary_timeframes failed")
        raise HTTPException(status_code=400, detail=f"Failed to get temporary timeframes: {exc}") from exc


@router.post("/publish_schedule")
def PublishSchedule(
    body: request_schemas.PublishScheduleRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    """Copy draft temporary_timeframes/temporary_room → timeframes/room for a symposium."""
    try:
        logger.info("publish_schedule: symposium_id=%s", body.symposium_id)

        departments_resp = read.get_departments(symposium_id=body.symposium_id)
        departments = cast(list[dict[str, Any]], departments_resp.data or [])
        department_ids = [UUID(str(d["id"])) for d in departments if d.get("id")]

        presentation_ids: list[UUID] = []
        all_presentations: list[dict[str, Any]] = []
        if department_ids:
            class_ids_list: list[UUID] = []
            classes_resp = read.get_classes(department_id=department_ids)
            for c in cast(list[dict[str, Any]], classes_resp.data or []):
                if c.get("id"):
                    class_ids_list.append(UUID(str(c["id"])))
            if class_ids_list:
                pres_resp = read.get_presentations(class_id=class_ids_list)
                all_presentations = cast(list[dict[str, Any]], pres_resp.data or [])
                presentation_ids = [UUID(str(p["id"])) for p in all_presentations if p.get("id")]

        if not presentation_ids:
            return {"status": "published", "count": 0}

        temp_tf_resp = read.get_temporary_timeframes(linked_id=presentation_ids)
        temp_tfs = cast(list[dict[str, Any]], temp_tf_resp.data or [])

        delete.delete_timeframes(presentation_ids)

        if temp_tfs:
            new_tf_rows: list[dict[str, str | int | UUID | datetime | date | None]] = [
                {
                    "id": uuid4(),
                    "linked_id": UUID(str(tf["linked_id"])),
                    "start_time": tf["start_time"],
                    "end_time": tf["end_time"],
                }
                for tf in temp_tfs
            ]
            write.insert("timeframes", new_tf_rows)

        room_updates: dict[UUID, str | int | None] = {
            UUID(str(p["id"])): p.get("temporary_room")
            for p in all_presentations
            if p.get("id")
        }
        if room_updates:
            write.update_column_by_ids("presentations", "room", room_updates)

        logger.info("publish_schedule complete: symposium_id=%s  timeframes=%d", body.symposium_id, len(temp_tfs))
        return {"status": "published", "count": len(temp_tfs)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("publish_schedule failed: symposium_id=%s", body.symposium_id)
        raise HTTPException(status_code=500, detail=f"Failed to publish schedule: {exc}") from exc


@router.put("/update_schedule_assignment")
def UpdateScheduleAssignment(
    payload: request_schemas.UpdateScheduleAssignmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int]:
    """Atomically update a presentation's room and time slot with conflict detection."""
    try:
        logger.info("update_schedule_assignment: presentation_id=%s  room=%s  symposium_id=%s", payload.presentation_id, payload.room, payload.symposium_id)
        presentation_id = str(payload.presentation_id)
        room_names = _load_room_names(payload.symposium_id)

        entities = LoadSymposiumEntities(payload.symposium_id)
        index = BuildConflictIndex(entities)

        target_pres = index.presentations_by_id.get(presentation_id)
        if target_pres is None:
            raise HTTPException(status_code=404, detail="Presentation not found in this symposium.")

        target_resources = index.ResourcesFor(target_pres)

        new_start = ensure_app_timezone(payload.start_time)
        new_end = ensure_app_timezone(payload.end_time)
        _assert_within_symposium_windows(payload.symposium_id, new_start, new_end)
        target_buffer = timedelta(minutes=int(target_pres.get("buffer") or 0))
        new_buffered_end = new_end + target_buffer

        other_pres_ids = [pid for pid in index.presentations_by_id if pid != presentation_id]

        if other_pres_ids:
            tf_resp = read.get_temporary_timeframes(
                linked_id=[UUID(pid) for pid in other_pres_ids]
            )
            other_timeframes = list(getattr(tf_resp, "data", None) or [])

            tf_by_pres: dict[str, dict[str, Any]] = {}
            for tf in other_timeframes:
                linked = str(tf.get("linked_id", ""))
                if linked:
                    tf_by_pres[linked] = tf

            for other_id, other in index.presentations_by_id.items():
                if other_id == presentation_id or other_id not in tf_by_pres:
                    continue

                other_tf = tf_by_pres[other_id]
                other_start = parse_app_datetime(other_tf["start_time"])
                other_end = parse_app_datetime(other_tf["end_time"])
                other_buffer = timedelta(minutes=int(other.get("buffer") or 0))
                other_buffered_end = other_end + other_buffer
                times_overlap = new_start < other_buffered_end and new_buffered_end > other_start

                if not times_overlap:
                    continue

                other_title = str(other.get("title", other_id))
                other_room = other.get("temporary_room")
                if other_room is not None and int(other_room) == payload.room:
                    raise HTTPException(
                        status_code=409,
                        detail=FormatRoomConflictSingle(
                            _room_label(room_names, payload.room), other_title,
                        ),
                    )

                shared = target_resources & index.ResourcesFor(other)
                if shared:
                    person_id = next(iter(shared))
                    raise HTTPException(
                        status_code=409,
                        detail=FormatPersonConflictSingle(
                            index.PersonRole(person_id),
                            index.PersonName(person_id),
                            other_title,
                        ),
                    )

        supabase.table("presentations").update(
            {"temporary_room": payload.room}
        ).eq("id", presentation_id).execute()

        delete.delete_temporary_timeframes(payload.presentation_id)

        write.insert("temporary_timeframes", [{
            "id": uuid4(),
            "linked_id": payload.presentation_id,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "symposium_id": payload.symposium_id,
        }])

        return {
            "status": "updated",
            "presentation_id": presentation_id,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("update_schedule_assignment failed: presentation_id=%s", payload.presentation_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to update schedule assignment: {exc}"
        ) from exc


@router.put("/bulk_update_schedule_assignments")
def BulkUpdateScheduleAssignments(
    payload: request_schemas.BulkUpdateScheduleAssignmentRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, object]:
    """Batch-update multiple presentation room/time assignments with conflict detection."""
    try:
        logger.info("bulk_update_schedule_assignments: symposium_id=%s  count=%d", payload.symposium_id, len(payload.assignments))
        room_names = _load_room_names(payload.symposium_id)
        assignment_map: dict[str, request_schemas.SingleScheduleAssignment] = {
            str(a.presentation_id): a for a in payload.assignments
        }

        entities = LoadSymposiumEntities(payload.symposium_id)
        index = BuildConflictIndex(entities)

        for pid in assignment_map:
            if pid not in index.presentations_by_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Presentation {pid} not found in this symposium.",
                )

        EffSlot = tuple[int, datetime, datetime]  # (room, start, buffered_end)
        effective: dict[str, EffSlot] = {}

        non_batch_ids = [
            UUID(pid) for pid in index.presentations_by_id
            if pid not in assignment_map
        ]
        existing_tf: dict[str, dict[str, Any]] = {}
        if non_batch_ids:
            tf_resp = read.get_temporary_timeframes(linked_id=non_batch_ids)
            for tf in list(getattr(tf_resp, "data", None) or []):
                linked = str(tf.get("linked_id", ""))
                if linked:
                    existing_tf[linked] = tf

        for pid, p in index.presentations_by_id.items():
            buf = timedelta(minutes=int(p.get("buffer") or 0))
            if pid in assignment_map:
                a = assignment_map[pid]
                start = ensure_app_timezone(a.start_time)
                end = ensure_app_timezone(a.end_time)
                _assert_within_symposium_windows(payload.symposium_id, start, end)
                effective[pid] = (a.room, start, end + buf)
            elif pid in existing_tf:
                room_val = p.get("temporary_room")
                if room_val is None:
                    continue
                tf = existing_tf[pid]
                start = parse_app_datetime(tf["start_time"])
                end = parse_app_datetime(tf["end_time"])
                effective[pid] = (int(room_val), start, end + buf)

        scheduled_ids = list(effective.keys())
        for i, pid_a in enumerate(scheduled_ids):
            room_a, start_a, buffered_end_a = effective[pid_a]
            pres_a = index.presentations_by_id[pid_a]
            resources_a = index.ResourcesFor(pres_a)

            for pid_b in scheduled_ids[i + 1:]:
                room_b, start_b, buffered_end_b = effective[pid_b]
                times_overlap = start_a < buffered_end_b and buffered_end_a > start_b
                if not times_overlap:
                    continue

                if pid_a not in assignment_map and pid_b not in assignment_map:
                    continue

                pres_b = index.presentations_by_id[pid_b]
                title_a = str(pres_a.get("title", pid_a))
                title_b = str(pres_b.get("title", pid_b))

                if room_a == room_b:
                    raise HTTPException(
                        status_code=409,
                        detail=FormatRoomConflictPair(
                            _room_label(room_names, room_a), title_a, title_b,
                        ),
                    )

                shared = resources_a & index.ResourcesFor(pres_b)
                if shared:
                    person_id = next(iter(shared))
                    raise HTTPException(
                        status_code=409,
                        detail=FormatPersonConflictPair(
                            index.PersonRole(person_id),
                            index.PersonName(person_id),
                            title_a, title_b,
                        ),
                    )

        batch_pids = [UUID(pid) for pid in assignment_map]
        delete.delete_temporary_timeframes(batch_pids)

        tf_rows: list[dict[str, str | int | UUID | datetime | date | None]] = []
        room_by_presentation: dict[UUID, str | int | None] = {}
        for pid, a in assignment_map.items():
            room_by_presentation[UUID(pid)] = a.room
            tf_rows.append({
                "id": uuid4(),
                "linked_id": UUID(pid),
                "start_time": a.start_time,
                "end_time": a.end_time,
                "symposium_id": payload.symposium_id,
            })

        if room_by_presentation:
            write.update_column_by_ids(
                "presentations", "temporary_room", room_by_presentation
            )

        if tf_rows:
            write.insert("temporary_timeframes", tf_rows)

        return {
            "status": "updated",
            "count": len(assignment_map),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.exception("bulk_update_schedule_assignments failed: symposium_id=%s", payload.symposium_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to bulk update schedule assignments: {exc}"
        ) from exc
