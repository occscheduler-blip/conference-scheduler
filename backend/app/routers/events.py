from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID

import pandas as pd
from fastapi import APIRouter, HTTPException
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas
from app.supabase_io.client import supabase

router = APIRouter(prefix="/events", tags=["events"])
SYMPOSIUM_DATAFRAMES: dict[int, dict[str, pd.DataFrame]] = {}


@router.post("/add_class")
def add_class(payload: request_schemas.AddClassRequest):
    try:
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
        return {
            "status": "Inserted",
            "class_id": class_def.id,
            "department_id": class_def.department_id,
            "records_inserted": {"classes": 1, "professors": len(professors_payload)},
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_department")
def add_department(payload: request_schemas.AddDepartmentRequest):
    try:
        department = supabase_schemas.Department(
            id=uuid4(),
            department_name=payload.department_name,
            department_head_name=payload.department_head_name,
            email=payload.email,
            symposium_id=payload.symposium_id,
        )

        resp = write.insert("departments", [department.model_dump()])
        print(resp)

        return {
            "status": "Inserted",
            "department_id": department.id,
            "symposium_id": department.symposium_id,
            "records_inserted": {"departments": 1},
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
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
        symposium_id = payload.symposium_id or uuid4()
        symposium = supabase_schemas.Symposium(
            id=symposium_id,
            name=payload.symposium_name,
            created_at=datetime.now(timezone.utc),
            rooms_available=payload.rooms_available,
        )
        symposium_payload = symposium.model_dump()

        # If the symposium already exists (fixed UUID edit flow), update it instead of failing.
        existing = supabase.table("symposiums").select("id").eq("id", str(symposium_id)).limit(1).execute()
        if existing.data:
            supabase.table("symposiums").update(
                {
                    "name": symposium_payload["name"],
                    "rooms_available": symposium_payload["rooms_available"],
                }
            ).eq("id", str(symposium_id)).execute()
        else:
            write.insert("symposiums", [symposium_payload])

        # Replace all existing timeframes for this symposium with the newly submitted set.
        delete.delete_timeframes(symposium_id)
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

        return {
            "status": "saved",
            "symposium_id": str(symposium_id),
            "name": payload.symposium_name,
            "records_inserted": {
                "symposiums": 1,
                "timeframes": len(timeframes),
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_students")
def add_students(payload: request_schemas.AddStudentsRequest):
    """Adds a list of students to the students table in the database."""
    try:
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
        return {
            "status": "inserted",
            "class_id": str(payload.class_id),
            "records_inserted": {
                "students": len(students),
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_presentation")
def add_presentation(payload: request_schemas.AddPresentationRequest):
    try:
        presentation_id = uuid4()
        presentation = supabase_schemas.Presentation(
            id=presentation_id,
            title=payload.title,
            class_id=payload.class_id,
            minutes=payload.minutes,
            start_time=None,
            end_time=None,
        )
        pres_resp = write.insert("presentations", [presentation.model_dump()])

        students: list[supabase_schemas.PresentingStudents] = []
        for student in payload.presenting_students:
            students.append(
                supabase_schemas.PresentingStudents(
                    id=uuid4(), presentation_id=presentation_id, student_id=student
                )
            )
        students_resp = write.insert(
            "presenting_students", [item.model_dump() for item in students]
        )

        return {
            "status": "inserted",
            "presentation_id": presentation_id,
            "class_id": payload.class_id,
            "records_inserted": {
                "presentations": 1,
                "presenting_students": len(students),
            },
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_prof_req")
def add_prof_request(payload: request_schemas.AddProfReqRequest):
    try:
        request = supabase_schemas.ProfRequest(
            id=uuid4(),
            student_id=payload.student_id,
            professor_id=payload.professor_id,
        )

        response = write.insert("prof_requests", [request.model_dump()])

        return {
            "status": "inserted",
            "student_id": payload.student_id,
            "professor_id": payload.professor_id,
            "records_inserted": {"prof_requests": 1},
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_timeframes")
def update_timeframes(payload: request_schemas.UpdateTimeframesRequest):
    if (
        payload.linked_id
        not in supabase.table("timeframes").select("linked_id", distinct=True).execute()
    ):
        raise ValueError("linked_id not in timeframes table.")

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

    return {
        "status": "updated",
        "linked_id": payload.linked_id,
        "records_deleted": {"timeframes": deleted_timeframes},
        "records_inserted": {"timeframes": len(timeframe_payload)},
    }


@router.get("/symposiums")
def get_symposiums():
    try:
        return read.get_symposiums()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/departments")
def get_departments(symposium_id: UUID | None = None):
    try:
        return read.get_departments(symposium_id=symposium_id)
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


@router.get("/prof_requests")
def get_prof_requests(student_id: UUID | None = None, professor_id: UUID | None = None):
    try:
        return read.get_prof_requests(student_id=student_id, professor_id=professor_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get professor requests: {exc}"
        ) from exc


@router.delete("/delete_symposium")
def delete_symposium(symposium_id: UUID):
    try:
        delete.delete_symposium(symposium_id)
        return {"status": "deleted", "records_deleted": {"symposiums": 1}}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete symposium: {exc}"
            ) from exc


@router.delete("/delete_department")
def delete_department(department_id: UUID):
    try:
        delete.delete_department(department_id)
        return {
            "status": "deleted",
            "records_deleted": {
                "departments": 1
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete department: {exc}"
            ) from exc
    

@router.delete("/delete_class")
def delete_class(class_id: UUID):
    try:
        delete.delete_class(class_id)
        return {
            "status": "deleted",
            "records_deleted": {
                "classes": 1
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete class: {exc}"
            ) from exc
    
@router.delete("/delete_student")
def delete_student(student_id: UUID):
    try:
        delete.delete_student(student_id)
        return {
            "status": "deleted",
            "records_deleted": {
                "students": 1
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete student: {exc}"
            ) from exc


@router.delete("/delete_professor")
def delete_professor(professor_id: UUID):
    try:
        delete.delete_professor(professor_id)
        return {
            "status": "deleted",
            "records_deleted": {
                "professors": 1
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete professor: {exc}"
            ) from exc


@router.delete("/delete_presentation")
def delete_presentation(presentation_id: UUID):
    try:
        delete.delete_presentation(presentation_id)
        return {
            "status": "deleted",
            "records_deleted": {
                "presentations": 1
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete presentation: {exc}"
            ) from exc
