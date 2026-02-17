from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator
from uuid import UUID

class Symposium(BaseModel):
    id: UUID
    created_at: datetime
    name: str

class DepartmentHead(BaseModel):
    id: UUID
    name: str
    email: str
    dept_name: str

class Class(BaseModel):
    id: UUID
    name: str

class Professor(BaseModel):
    id: UUID
    name: str
    email: str
    class_id: UUID

class Student(BaseModel):
    id: UUID
    name: str
    email: str
    class_id: UUID
    presentation_id: UUID | None

class Presentation(BaseModel):
    id: UUID
    title: str
    class_id: UUID
    start_time: datetime
    end_time: datetime

class Timeframes(BaseModel):
    id: UUID
    start_time: datetime
    end_time: datetime
    symposium_id: UUID | None = None
    prof_id: UUID | None = None
    student_id: UUID | None = None

class PresentingStudents(BaseModel):
    presentation_id: UUID
    student_id: UUID

class ProfRequests(BaseModel):
    student_id: UUID
    prof_id: UUID


class TimeframeWindow(BaseModel):
    start_time: datetime
    end_time: datetime


class AddSymposiumRequest(BaseModel):
    symposium_name: str
    rooms_available: int
    timeframes: list[TimeframeWindow]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symposium_name": "Spring Symposium",
                "rooms_available": 5,
                "timeframes": [
                    {
                        "start_time": "2026-04-20T09:00:00Z",
                        "end_time": "2026-04-20T12:00:00Z",
                    },
                    {
                        "start_time": "2026-04-21T13:00:00Z",
                        "end_time": "2026-04-21T16:00:00Z",
                    },
                ],
            }
        }
    )
