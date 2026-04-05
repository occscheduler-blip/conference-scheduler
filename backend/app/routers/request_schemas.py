from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.supabase_io.client import supabase

# NOTE: This is possibly not necessary and for now is just an arbitrary value, we can determine what the real max is later.
MAX_ROOMS = 100
MAX_TIME = 60
MAX_PRESENTING_STUDENTS = 10


class TimeframeWindow(BaseModel):
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def end_after_start(self) -> "TimeframeWindow":
        if self.end_time < self.start_time:
            raise ValueError(
                "Timeframe start time must come before timeframe end time."
            )
        return self


class AddSymposiumRequest(BaseModel):
    symposium_id: UUID | None = None
    symposium_name: str
    rooms_available: int
    timeframes: list[TimeframeWindow]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symposium_id": "9e1fd0da-ea43-48f2-85df-5281a495f054",
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
    def validate_symposium_name(cls, symposium_name: str) -> str:
        name = symposium_name.strip()
        if not name:
            raise ValueError("Symposium name cannot be empty.")
        return name

    @field_validator("rooms_available")
    @classmethod
    def validate_rooms_available(cls, rooms_available: int) -> int:
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
    def validate_dept_name(cls, dept_name: str) -> str:
        name = dept_name.strip()
        if not name:
            raise ValueError("Department name cannot be empty")
        return name

    @field_validator("department_head_name")
    @classmethod
    def validate_dept_head_name(cls, dept_head_name: str) -> str:
        name = dept_head_name.strip()
        if not name:
            raise ValueError("Department head name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        email = email.strip().lower()
        if not email:
            raise ValueError("Email cannot be blank.")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symposium_id": "9e1fd0da-ea43-48f2-85df-5281a495f054",
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
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        return name


class UpdateDepartmentRequest(BaseModel):
    department_id: UUID
    department_name: str
    department_head_name: str
    email: str

    @field_validator("department_name")
    @classmethod
    def validate_dept_name(cls, dept_name: str) -> str:
        name = dept_name.strip()
        if not name:
            raise ValueError("Department name cannot be empty")
        return name

    @field_validator("department_head_name")
    @classmethod
    def validate_dept_head_name(cls, dept_head_name: str) -> str:
        name = dept_head_name.strip()
        if not name:
            raise ValueError("Department head name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        email = email.strip().lower()
        if not email:
            raise ValueError("Email cannot be blank.")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email


class AddClassRequest(BaseModel):
    name: str
    department_id: UUID
    professors: list[ProfessorInit]

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        return name

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "department_id": "ba16476b-e00e-4eeb-98e6-d78be76bfd41",
                "name": "BIO101: Intro to Biology",
                "professors": [
                    {
                        "name": "John Smith",
                        "email": "jsmith@hamilton.edu",
                    },
                    {
                        "name": "Jane Doe",
                        "email": "jdoe@hamilton.edu",
                    },
                ],
            },
        }
    )


class StudentInit(BaseModel):
    name: str
    email: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        email = email.strip().lower()
        if not email:
            raise ValueError("Email cannot be blank.")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email


class AddStudentsRequest(BaseModel):
    class_id: UUID
    students: list[StudentInit]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "class_id": "a2d9911c-977b-457f-81dc-672490e4f2ab",
                "students": [
                    {
                        "name": "Jim Brown",
                        "email": "jbrown@hamilton.edu",
                    },
                    {
                        "name": "George Washington",
                        "email": "gwashing@hamilton.edu",
                    },
                ],
            }
        }
    )


class AddPresentationRequest(BaseModel):
    title: str
    class_id: UUID
    minutes: int
    buffer: int = 0
    presenting_students: list[UUID]

    @field_validator("title")
    @classmethod
    def validate_title(cls, title: str) -> str:
        title = title.strip()
        if not title:
            raise ValueError("Title cannot be empty")
        return title

    @field_validator("minutes")
    @classmethod
    def validate_minutes(cls, minutes: int) -> int:
        if minutes > MAX_TIME or minutes < 1:
            raise ValueError(f"Presentations must be between 1 and {MAX_TIME}")
        return minutes

    @field_validator("buffer")
    @classmethod
    def validate_buffer(cls, buffer: int) -> int:
        if buffer < 0:
            raise ValueError("Buffer must be 0 or greater")
        return buffer

    @field_validator("presenting_students")
    @classmethod
    def validate_presenting_students(cls, presenting_students: list[UUID]) -> list[UUID]:
        if len(presenting_students) > MAX_PRESENTING_STUDENTS:
            raise ValueError(
                f"No more than {MAX_PRESENTING_STUDENTS} can present one presentation"
            )
        return presenting_students

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Bio Thesis Presentation",
                "class_id": "a2d9911c-977b-457f-81dc-672490e4f2ab",
                "minutes": 20,
                "presenting_students": [
                    "6015d279-a271-4d9d-9c8e-435731caac04",
                    "a4b08f01-9cea-4e35-9d9e-0e664f35d4ef",
                ],
            }
        }
    )


class AddReqRequest(BaseModel):
    name: str
    email: str
    student_id: UUID
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "John Smith",
                "email": "jsmith@hamilton.edu",
                "student_id": "<The requesting student's UUID>",
            }
        }
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Student name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        if email is None:
            return email
        email = email.strip().lower()
        if not email:
            raise ValueError("Email cannot be blank.")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email


class UpdateTimeframesRequest(BaseModel):
    linked_id: UUID
    timeframes: list[TimeframeWindow]


class UpdateStudentRequest(BaseModel):
    student_id: UUID
    name: str
    email: str
    class_id: UUID
    presentation_id: UUID

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Student name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        email = email.strip().lower()
        if not email:
            raise ValueError("Email cannot be blank.")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email


class UpdateProfessorRequest(BaseModel):
    professor_id: UUID
    name: str
    email: str
    class_id: UUID

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Professor name cannot be empty")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        email = email.strip().lower()
        if not email:
            raise ValueError("Email cannot be blank.")
        if not email.endswith("@hamilton.edu"):
            raise ValueError("Email must be a @hamilton.edu address.")
        return email


class UpdateClassRequest(BaseModel):
    class_id: UUID
    name: str
    department_id: UUID

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        return name


class UpdateSymposiumRequest(BaseModel):
    symposium_id: UUID
    symposium_name: str
    rooms_available: int

    @field_validator("symposium_name")
    @classmethod
    def validate_symposium_name(cls, symposium_name: str) -> str:
        symposium_name = symposium_name.strip()
        if not symposium_name:
            raise ValueError("Symposium name cannot be empty.")
        return symposium_name

    @field_validator("rooms_available")
    @classmethod
    def validate_rooms_available(cls, rooms_available: int) -> int:
        if rooms_available > MAX_ROOMS:
            raise ValueError(f"You may not choose more than {MAX_ROOMS} rooms.")
        return rooms_available


class UpdatePresentationRequest(BaseModel):
    presentation_id: UUID
    title: str
    class_id: UUID
    minutes: int
    presenting_students: list[UUID]

    @field_validator("title")
    @classmethod
    def validate_title(cls, title: str) -> str:
        title = title.strip()
        if not title:
            raise ValueError("Title cannot be empty")
        return title

    @field_validator("minutes")
    @classmethod
    def validate_minutes(cls, minutes: int) -> int:
        if minutes > MAX_TIME or minutes < 1:
            raise ValueError(f"Presentations must be between 1 and {MAX_TIME}")
        return minutes

    @field_validator("presenting_students")
    @classmethod
    def validate_presenting_students(cls, presenting_students: list[UUID]) -> list[UUID]:
        if len(presenting_students) > MAX_PRESENTING_STUDENTS:
            raise ValueError(
                f"No more than {MAX_PRESENTING_STUDENTS} can present one presentation"
            )
        return presenting_students


class BasicScheduleParticipant(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Participant name cannot be empty")
        return name


class BasicScheduleWindow(BaseModel):
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def end_after_start(self) -> "BasicScheduleWindow":
        if self.end_time <= self.start_time:
            raise ValueError("Window end time must come after start time.")
        return self


class BasicScheduleRequest(BaseModel):
    day_start: datetime
    day_end: datetime
    presentation_minutes: int
    students: list[BasicScheduleParticipant]
    room_count: int = 1
    professor_name: str | None = None
    professor_unavailable: list[BasicScheduleWindow] = Field(default_factory=list)
    slot_minutes: int = 5

    @model_validator(mode="after")
    def validate_day_window(self) -> "BasicScheduleRequest":
        if self.day_end <= self.day_start:
            raise ValueError("day_end must be after day_start.")
        return self

    @field_validator("presentation_minutes")
    @classmethod
    def validate_presentation_minutes(cls, presentation_minutes: int) -> int:
        if presentation_minutes < 1 or presentation_minutes > MAX_TIME:
            raise ValueError(f"Presentations must be between 1 and {MAX_TIME}")
        return presentation_minutes

    @field_validator("students")
    @classmethod
    def validate_students(
        cls, students: list[BasicScheduleParticipant]
    ) -> list[BasicScheduleParticipant]:
        if not students:
            raise ValueError("At least one student is required.")
        return students

    @field_validator("room_count")
    @classmethod
    def validate_room_count(cls, room_count: int) -> int:
        if room_count < 1 or room_count > MAX_ROOMS:
            raise ValueError(f"Room count must be between 1 and {MAX_ROOMS}.")
        return room_count

    @field_validator("slot_minutes")
    @classmethod
    def validate_slot_minutes(cls, slot_minutes: int) -> int:
        if slot_minutes < 1 or slot_minutes > MAX_TIME:
            raise ValueError(f"Slot minutes must be between 1 and {MAX_TIME}.")
        return slot_minutes
