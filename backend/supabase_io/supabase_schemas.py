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


class Timeframe(BaseModel):
    id: UUID
    start_time: datetime
    end_time: datetime

class PresentingStudents(BaseModel):
    presentation_id: UUID
    student_id: UUID

class ProfRequests(BaseModel):
    student_id: UUID
    prof_id: UUID