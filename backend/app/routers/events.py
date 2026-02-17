from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, HTTPException
from app.supabase_io import delete, write

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas

router = APIRouter(prefix="/events", tags=["events"])
SYMPOSIUM_DATAFRAMES: dict[int, dict[str, pd.DataFrame]] = {}

@router.post("/add_class")
def add_class(payload: request_schemas.AddClassRequest):
    try:
        class_id = uuid4()
        class_def = supabase_schemas.Class(
            id=class_id,
            name=payload.name,
            department_id=payload.department_id
        )
        class_resp = write.insert("classes", [class_def.model_dump()])
        professors = [
            supabase_schemas.Professor(
                id=uuid4(),
                name=professor.name,
                email=professor.email,
                class_id=class_id
            )
            for professor in payload.professors
        ]
        professors_payload = [professor.model_dump() for professor in professors]
        prof_resp = write.insert("professors", professors_payload)
        return {
            "status": "Inserted",
            "class_id": class_def.id,
            "department_id": class_def.department_id,
            "records_inserted": {
                "classes": 1,
                "professors": len(professors_payload)
            }
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc

@router.post("/add_department")
def add_department(payload: request_schemas.AddDepartmentRequest):
    try:
        department = supabase_schemas.Department(
            id=uuid4(),
            department_name=payload.department_name,
            department_head_name=payload.department_head_name,
            email=payload.email,
            symposium_id=payload.symposium_id
        )

        resp = write.insert("departments", [department.model_dump()])
        print(resp)

        return {
            "status": "Inserted",
            "department_id": department.id,
            "symposium_id": department.symposium_id,
            "records_inserted": {
                "departments": 1
            }
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc

@router.post("/add_symposium")
def add_symposium(payload: request_schemas.AddSymposiumRequest):
    """Validate symposium + timeframe data and insert into Supabase tables.

    Args:
        payload (schemas.AddSymposiumRequest): symposium request payload.

    Returns:
        dict[str, Any]: status payload with inserted record counts.
    """
    try:
        symposium_id = uuid4()
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

        symposium = supabase_schemas.Symposium(
            id=symposium_id,
            name=payload.symposium_name,
            created_at = datetime.now(timezone.utc),
            rooms_available=payload.rooms_available,
        )

        response = write.insert("symposiums", [symposium.model_dump()])

        return {
            "status": "inserted",
            "symposium_id": str(symposium_id),
            "name": symposium.name,
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
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc

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
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc
    
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
            end_time=None
        )
        pres_resp = write.insert("presentations", [presentation.model_dump()])

        students: list[supabase_schemas.PresentingStudents] = []
        for student in payload.presenting_students:
            students.append(supabase_schemas.PresentingStudents(
                id=uuid4(),
                presentation_id=presentation_id,
                student_id=student
            ))
        students_resp = write.insert("presenting_students", [item.model_dump() for item in students])

        return {
            "status": "inserted",
            "presentation_id": presentation_id,
            "class_id": payload.class_id,
            "records_inserted": {
                "presentations": 1,
                "presenting_students": len(students)
            }
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc
