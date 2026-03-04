import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID

import pandas as pd
from fastapi import APIRouter, HTTPException
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["events"])
SYMPOSIUM_DATAFRAMES: dict[int, dict[str, pd.DataFrame]] = {}


def _serialize_update_fields(fields: dict):
    serialized: dict = {}
    for key, value in fields.items():
        if isinstance(value, UUID):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def _rows_affected(response, fallback: int = 0) -> int:
    """Return rows affected from a Supabase response object."""
    if isinstance(response, dict):
        count = response.get("count")
        if isinstance(count, int) and count >= 0:
            return count

        data = response.get("data")
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return 1

        return fallback

    count = getattr(response, "count", None)
    if isinstance(count, int) and count >= 0:
        return count

    data = getattr(response, "data", None)
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return 1

    return fallback


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


@router.post("/add_class")
def add_class(payload: request_schemas.AddClassRequest):
    try:
        logger.info("Creating class '%s' in department %s", payload.name, payload.department_id)
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
        logger.info("Created class %s with %d professor(s)", class_id, professors_inserted)
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
        logger.warning("Validation error in add_class: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to create class: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_department")
def add_department(payload: request_schemas.AddDepartmentRequest):
    try:
        logger.info(
            "Creating department '%s' in symposium %s",
            payload.department_name,
            payload.symposium_id,
        )
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
        logger.info("Created department %s", department.id)
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
        logger.warning("Validation error in add_department: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to create department: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_symposium")
def add_symposium(payload: request_schemas.AddSymposiumRequest):
    """Validate symposium + timeframe data and insert into Supabase tables.

    Args:
        payload (schemas.AddSymposiumRequest): symposium request payload.

    Returns:
        dict[str, Any]: status payload with inserted record counts.
    """
    try:
        logger.info("Creating symposium '%s'", payload.symposium_name)
        symposium_id = uuid4()
        symposium = supabase_schemas.Symposium(
            id=symposium_id,
            name=payload.symposium_name,
            created_at=datetime.now(timezone.utc),
            rooms_available=payload.rooms_available,
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

        logger.info(
            "Created symposium %s with %d timeframe(s)", symposium_id, timeframes_inserted
        )
        return {
            "status": "saved",
            "symposium_id": str(symposium_id),
            "name": payload.symposium_name,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Validation error in add_symposium: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to create symposium: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_students")
def add_students(payload: request_schemas.AddStudentsRequest):
    """Adds a list of students to the students table in the database."""
    try:
        logger.info("Adding %d student(s) to class %s", len(payload.students), payload.class_id)
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
        logger.info("Added %d student(s) to class %s", students_inserted, payload.class_id)
        return {
            "status": "inserted",
            "class_id": str(payload.class_id),
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Validation error in add_students: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to add students: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_presentation")
def add_presentation(payload: request_schemas.AddPresentationRequest):
    try:
        logger.info(
            "Creating presentation '%s' for class %s with %d student(s)",
            payload.title,
            payload.class_id,
            len(payload.presenting_students),
        )
        presentation_id = uuid4()
        presentation_payload = {
            "id": presentation_id,
            "title": payload.title,
            "class_id": payload.class_id,
            "minutes": payload.minutes,
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

        logger.info("Created presentation %s", presentation_id)
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
        logger.warning("Validation error in add_presentation: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to create presentation: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_request")
def add_prof_request(payload: request_schemas.AddReqRequest):
    try:
        logger.info(
            "Student %s submitting professor request for '%s' (%s)",
            payload.student_id,
            payload.name,
            payload.email,
        )
        request = supabase_schemas.Request(
            id=uuid4(),
            name=payload.name,
            email=payload.email,
            student_id=payload.student_id
        )

        response = write.insert("requests", [request.model_dump()])
        prof_requests_inserted = _rows_affected(response, fallback=1)
        records_inserted = {"prof_requests": prof_requests_inserted}
        logger.info("Saved professor request %s", request.id)
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
        logger.warning("Validation error in add_request: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to add professor request: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_timeframes")
def update_timeframes(payload: request_schemas.UpdateTimeframesRequest):
    try:
        logger.info(
            "Replacing timeframes for linked_id=%s (%d new window(s))",
            payload.linked_id,
            len(payload.timeframes),
        )
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

        logger.info(
            "Updated timeframes for linked_id=%s: deleted=%d inserted=%d",
            payload.linked_id,
            deleted_timeframes,
            timeframes_inserted,
        )
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
        logger.warning("Validation error in update_timeframes: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update timeframes: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update timeframes: {exc}"
        ) from exc


@router.put("/update_student")
def update_student(payload: request_schemas.UpdateStudentRequest):
    try:
        logger.info("Updating student %s", payload.student_id)
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

        logger.info("Updated student %s: fields=%s", payload.student_id, sorted(update_payload.keys()))
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
        logger.warning("Validation error in update_student: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update student %s: %s", payload.student_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to update student: {exc}"
        ) from exc


@router.put("/update_professor")
def update_professor(payload: request_schemas.UpdateProfessorRequest):
    try:
        logger.info("Updating professor %s", payload.professor_id)
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

        logger.info("Updated professor %s: fields=%s", payload.professor_id, sorted(update_payload.keys()))
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
        logger.warning("Validation error in update_professor: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update professor %s: %s", payload.professor_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to update professor: {exc}"
        ) from exc


@router.put("/update_class")
def update_class(payload: request_schemas.UpdateClassRequest):
    try:
        logger.info("Updating class %s", payload.class_id)
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

        logger.info("Updated class %s: fields=%s", payload.class_id, sorted(update_payload.keys()))
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
        logger.warning("Validation error in update_class: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update class %s: %s", payload.class_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to update class: {exc}"
        ) from exc


@router.put("/update_department")
def update_department(payload: request_schemas.UpdateDepartmentRequest):
    try:
        logger.info("Updating department %s", payload.department_id)
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
            "departments": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        logger.info("Updated department %s", payload.department_id)
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
        logger.warning("Validation error in update_department: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update department %s: %s", payload.department_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to update department: {exc}"
        ) from exc


@router.put("/update_symposium")
def update_symposium(payload: request_schemas.UpdateSymposiumRequest):
    try:
        logger.info("Updating symposium %s", payload.symposium_id)
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"symposium_id"},
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

        logger.info("Updated symposium %s: fields=%s", payload.symposium_id, sorted(update_payload.keys()))
        return {
            "status": "updated",
            "symposium_id": str(payload.symposium_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Validation error in update_symposium: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update symposium %s: %s", payload.symposium_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to update symposium: {exc}"
        ) from exc


@router.put("/update_presentation")
def update_presentation(payload: request_schemas.UpdatePresentationRequest):
    try:
        logger.info("Updating presentation %s", payload.presentation_id)
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

        logger.info(
            "Updated presentation %s: fields=%s presenting_students_replaced=%s",
            payload.presentation_id,
            sorted(update_payload.keys()),
            payload.presenting_students is not None,
        )
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
        logger.warning("Validation error in update_presentation: %s", exc)
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        logger.error("Failed to update presentation %s: %s", payload.presentation_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to update presentation: {exc}"
        ) from exc


@router.get("/symposiums")
def get_symposiums():
    try:
        response = read.get_symposiums()
        rows = list(getattr(response, "data", None) or [])
        return {"data": rows, "symposiums": rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/symposiums/{symposium_id}")
def get_symposium(symposium_id: UUID):
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
            logger.warning("Symposium %s not found", symposium_id)
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


@router.get("/departments")
def get_departments(symposium_id: UUID | None = None):
    try:
        response = read.get_departments(symposium_id=symposium_id)
        rows = list(getattr(response, "data", None) or [])
        return {"data": rows, "departments": rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/classes")
def get_classes(department_id: UUID | None = None):
    try:
        return read.get_classes(department_id=department_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get classes: {exc}"
        ) from exc


@router.get("/students")
def get_students(class_id: UUID | None = None):
    try:
        return read.get_students(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get students: {exc}"
        ) from exc


@router.get("/presentations")
def get_presentations(class_id: UUID | None = None):
    try:
        return read.get_presentations(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get presentations: {exc}"
        ) from exc


@router.get("/professors")
def get_professors(class_id: UUID | None = None):
    try:
        return read.get_professors(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get professors: {exc}"
        ) from exc


@router.get("/timeframes")
def get_timeframes(linked_id: UUID | None = None):
    try:
        return read.get_timeframes(linked_id=linked_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get timeframes: {exc}"
        ) from exc


@router.get("/requests")
def get_requests(student_id: UUID | None = None):
    try:
        return read.get_requests(student_id=student_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get professor requests: {exc}"
        ) from exc


@router.get("/requests")
def get_requests(student_id: UUID | None = None):
    try:
        return read.get_requests(student_id=student_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get requests: {exc}"
        ) from exc


@router.delete("/delete_symposium")
def delete_symposium(symposium_id: UUID):
    try:
        logger.info("Deleting symposium %s", symposium_id)
        counts = _normalize_counts(
            delete.delete_symposium(symposium_id), {"symposiums": 1}
        )
        logger.info("Deleted symposium %s → %s", symposium_id, counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete symposium %s: %s", symposium_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete symposium: {exc}"
        ) from exc


@router.delete("/delete_department")
def delete_department(department_id: UUID):
    try:
        logger.info("Deleting department %s", department_id)
        counts = _normalize_counts(
            delete.delete_department(department_id), {"departments": 1}
        )
        logger.info("Deleted department %s → %s", department_id, counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete department %s: %s", department_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete department: {exc}"
        ) from exc


@router.delete("/delete_class")
def delete_class(class_id: UUID):
    try:
        logger.info("Deleting class %s", class_id)
        counts = _normalize_counts(delete.delete_class(class_id), {"classes": 1})
        logger.info("Deleted class %s → %s", class_id, counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete class %s: %s", class_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete class: {exc}"
        ) from exc


@router.delete("/delete_student")
def delete_student(student_id: UUID):
    try:
        logger.info("Deleting student %s", student_id)
        counts = _normalize_counts(delete.delete_student(student_id), {"students": 1})
        logger.info("Deleted student %s → %s", student_id, counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete student %s: %s", student_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete student: {exc}"
        ) from exc


@router.delete("/delete_professor")
def delete_professor(professor_id: UUID):
    try:
        logger.info("Deleting professor %s", professor_id)
        counts = _normalize_counts(
            delete.delete_professor(professor_id), {"professors": 1}
        )
        logger.info("Deleted professor %s → %s", professor_id, counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete professor %s: %s", professor_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete professor: {exc}"
        ) from exc


@router.delete("/delete_presentation")
def delete_presentation(presentation_id: UUID):
    try:
        logger.info("Deleting presentation %s", presentation_id)
        counts = _normalize_counts(
            delete.delete_presentation(presentation_id), {"presentations": 1}
        )
        logger.info("Deleted presentation %s → %s", presentation_id, counts)
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete presentation %s: %s", presentation_id, exc, exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to delete presentation: {exc}"
        ) from exc
