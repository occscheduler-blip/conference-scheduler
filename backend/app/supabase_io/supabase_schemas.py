from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator
from uuid import UUID


class Symposium(BaseModel):
    id: UUID
    created_at: datetime
    name: str
    rooms_available: int
    default_buffer: int


class Department(BaseModel):
    id: UUID
    department_name: str
    department_head_name: str
    email: str
    symposium_id: UUID


class Class(BaseModel):
    id: UUID
    name: str
    department_id: UUID


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
    minutes: int
    buffer: int
    start_time: datetime | None
    end_time: datetime | None


class Timeframe(BaseModel):
    id: UUID
    linked_id: UUID
    start_time: datetime
    end_time: datetime


class PresentingStudents(BaseModel):
    id: UUID
    presentation_id: UUID
    student_id: UUID


class Request(BaseModel):
    id: UUID
    name: str
    email: str
    student_id: UUID
