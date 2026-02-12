from datetime import datetime

from pydantic import BaseModel

class Professor(BaseModel):
    id: int
    name: str
    email: str
    availability: list[tuple[datetime, datetime]] | None = None

class Student(BaseModel):
    id: int
    name: str
    email: str
    prof_requests: list[Professor]
    availability: list[tuple[datetime, datetime]] | None = None

class Presentation(BaseModel):
    id: int
    title: str
    students: list[Student]
    professors: list[Professor]
    minutes: int

class Chair(BaseModel):
    id: int
    name: str
    email: str

class Class(BaseModel):
    id: int
    name: str
    professors: list[Professor]
    students: list[Student]
    presentations: list[Presentation]

class Department(BaseModel):
    id: int
    name: str
    chair: Chair
    classes: list[Class]

class Symposium(BaseModel):
    id: int
    name: str
    departments: list[Department]
