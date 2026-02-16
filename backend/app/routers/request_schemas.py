from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, field_validator

class TimeframeWindow(BaseModel):
    start_time: datetime
    end_time: datetime

class SymposiumCreatePayload(BaseModel):
    symposium_name: str
    rooms: int
    timeframes: list[tuple[datetime, datetime]]

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

class AddDepartmentRequest(BaseModel):
    symposium: uuid.UUID
    department_name: str
    department_head_name: str
    email: str

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
                "symposium": "<a UUID>",
                "department_name": "Biology",
                "department_head_name": "John Smith",
                "email": "jsmith@hamilton.edu",
            },
        }
    )