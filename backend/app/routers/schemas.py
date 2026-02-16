from datetime import datetime

from pydantic import BaseModel, model_validator
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

    @model_validator(mode="after")
    def _validate_owner_link(self) -> "Timeframes":
        owner_ids = [self.symposium_id, self.prof_id, self.student_id]
        if sum(owner_id is not None for owner_id in owner_ids) != 1:
            raise ValueError(
                "Timeframe must be linked to exactly one of symposium_id, prof_id, or student_id."
            )
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        return self

class PresentingStudents(BaseModel):
    presentation_id: UUID
    student_id: UUID

class ProfRequests(BaseModel):
    student_id: UUID
    prof_id: UUID
