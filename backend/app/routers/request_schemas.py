from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# NOTE: This is possibly not necessary and for now is just an arbitrary value, we can determine what the real max is later.
MAX_ROOMS = 100

class TimeframeWindow(BaseModel):
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_time < self.start_time:
            raise ValueError("Timeframe start time must come before timeframe end time.")
        return self
        

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

    @field_validator("symposium_name")
    @classmethod
    def validate_symposium_name(cls, symposium_name: str):
        name = symposium_name.strip()
        if not name:
            raise ValueError("Symposium name cannot be empty.")
        return name
    
    @field_validator("rooms_available")
    @classmethod
    def validate_rooms_available(cls, rooms_available: int):
        if rooms_available > MAX_ROOMS:
            raise ValueError(f"You may not choose more than {MAX_ROOMS} rooms.")
        return rooms_available
    

class AddDepartmentRequest(BaseModel):
    symposium_id: UUID
    department_name: str
    department_head_name: str
    email: str

    @field_validator("department_name")
    @classmethod
    def validate_dept_name(cls, dept_name: str):
        name = dept_name.strip()
        if not name:
            raise ValueError("Department name cannot be empty")
        return name
    
    @field_validator("department_head_name")
    @classmethod
    def validate_dept_head_name(cls, dept_head_name: str):
        name = dept_head_name.strip()
        if not name:
            raise ValueError("Department head name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str):
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError("Invalid email")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symposium": "9e1fd0da-ea43-48f2-85df-5281a495f054",
                "department_name": "Biology",
                "department_head_name": "John Smith",
                "email": "jsmith@hamilton.edu",
            },
        }
    )


class ProfessorInit(BaseModel):
    name: str
    email: str
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str):
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        return name
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str):
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError("Invalid email")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email


class AddClassRequest(BaseModel):
    name: str
    department_id: UUID
    professors: list[ProfessorInit]

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str):
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        return name
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "department_id": "bc9e68ae-85aa-4d31-ace8-f8450ece617c",
                "name": "BIO101: Intro to Biology",
                "professors": [
                    {
                        "name": "John Smith",
                        "email": "jsmith@hamilton.edu",
                    },
                    {
                        "name": "Jane Doe",
                        "email": "jdoe@hamilton.edu",
                    }
                ]
            },
        }
    )
    
    
class AddStudentsRequest(BaseModel):
    class_id: UUID
    
