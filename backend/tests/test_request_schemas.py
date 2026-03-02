from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.request_schemas import (
    AddClassRequest,
    AddDepartmentRequest,
    AddPresentationRequest,
    AddStudentsRequest,
    AddSymposiumRequest,
    MAX_PRESENTING_STUDENTS,
    MAX_ROOMS,
    MAX_TIME,
)


def _window(start_hour: int, end_hour: int):
    return {
        "start_time": datetime(2026, 4, 20, start_hour, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 4, 20, end_hour, 0, tzinfo=timezone.utc),
    }


def test_add_symposium_request_normalizes_name_and_accepts_valid_payload():
    payload = AddSymposiumRequest(
        symposium_name="  Spring Symposium  ",
        rooms_available=5,
        timeframes=[_window(9, 11)],
    )
    assert payload.symposium_name == "Spring Symposium"


def test_add_symposium_request_rejects_blank_name():
    with pytest.raises(ValidationError):
        AddSymposiumRequest(
            symposium_name="   ",
            rooms_available=5,
            timeframes=[_window(9, 11)],
        )


def test_add_symposium_request_rejects_too_many_rooms():
    with pytest.raises(ValidationError):
        AddSymposiumRequest(
            symposium_name="Spring Symposium",
            rooms_available=MAX_ROOMS + 1,
            timeframes=[_window(9, 11)],
        )


def test_add_symposium_request_rejects_end_before_start():
    with pytest.raises(ValidationError):
        AddSymposiumRequest(
            symposium_name="Spring Symposium",
            rooms_available=4,
            timeframes=[_window(11, 10)],
        )


def test_add_department_request_enforces_hamilton_email():
    with pytest.raises(ValidationError):
        AddDepartmentRequest(
            symposium_id=uuid4(),
            department_name="Biology",
            department_head_name="Prof. Smith",
            email="prof@gmail.com",
        )


def test_add_class_request_preserves_professor_email():
    req = AddClassRequest(
        name="BIO101",
        department_id=uuid4(),
        professors=[{"name": "Prof", "email": "PROF@Hamilton.edu"}],
    )
    assert req.professors[0].email == "PROF@Hamilton.edu"


def test_add_students_request_validates_student_email_domain():
    with pytest.raises(ValidationError):
        AddStudentsRequest(
            class_id=uuid4(),
            students=[{"name": "Student", "email": "student@example.com"}],
        )


def test_add_presentation_request_validates_minutes_range():
    with pytest.raises(ValidationError):
        AddPresentationRequest(
            title="Talk",
            class_id=uuid4(),
            minutes=MAX_TIME + 1,
            presenting_students=[uuid4()],
        )


def test_add_presentation_request_validates_presenting_students_count():
    with pytest.raises(ValidationError):
        AddPresentationRequest(
            title="Talk",
            class_id=uuid4(),
            minutes=20,
            presenting_students=[uuid4() for _ in range(MAX_PRESENTING_STUDENTS + 1)],
        )
