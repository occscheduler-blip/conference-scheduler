"""Tests for request_schemas – Pydantic validation rules."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.request_schemas import (
    MAX_PRESENTING_STUDENTS,
    MAX_ROOMS,
    MAX_TIME,
    AddClassRequest,
    AddDepartmentRequest,
    AddPresentationRequest,
    AddReqRequest,
    AddStudentsRequest,
    AddSymposiumRequest,
    ProfessorInit,
    StudentInit,
    TimeframeWindow,
    UpdateClassRequest,
    UpdateDepartmentRequest,
    UpdatePresentationRequest,
    UpdateProfessorRequest,
    UpdateStudentRequest,
    UpdateSymposiumRequest,
    UpdateTimeframesRequest,
)


NOW = datetime.now(timezone.utc)
LATER = NOW + timedelta(hours=3)
UUID1 = uuid4()
UUID2 = uuid4()


# ---------------------------------------------------------------------------
# TimeframeWindow
# ---------------------------------------------------------------------------
class TestTimeframeWindow:
    def test_valid(self):
        tw = TimeframeWindow(start_time=NOW, end_time=LATER)
        assert tw.start_time == NOW

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError, match="start time must come before"):
            TimeframeWindow(start_time=LATER, end_time=NOW)

    def test_equal_times_accepted(self):
        # end == start should not raise (not strictly "before")
        tw = TimeframeWindow(start_time=NOW, end_time=NOW)
        assert tw.start_time == tw.end_time


# ---------------------------------------------------------------------------
# AddSymposiumRequest
# ---------------------------------------------------------------------------
class TestAddSymposiumRequest:
    def test_valid_minimal(self):
        req = AddSymposiumRequest(
            symposium_name="Spring",
            rooms_available=5,
            timeframes=[{"start_time": NOW, "end_time": LATER}],
        )
        assert req.symposium_name == "Spring"
        assert req.symposium_id is None

    def test_with_optional_id(self):
        req = AddSymposiumRequest(
            symposium_id=UUID1,
            symposium_name="Fall",
            rooms_available=1,
            timeframes=[],
        )
        assert req.symposium_id == UUID1

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            AddSymposiumRequest(
                symposium_name="   ",
                rooms_available=1,
                timeframes=[],
            )

    def test_too_many_rooms_raises(self):
        with pytest.raises(ValidationError, match="rooms"):
            AddSymposiumRequest(
                symposium_name="X",
                rooms_available=MAX_ROOMS + 1,
                timeframes=[],
            )

    def test_max_rooms_accepted(self):
        req = AddSymposiumRequest(
            symposium_name="X",
            rooms_available=MAX_ROOMS,
            timeframes=[],
        )
        assert req.rooms_available == MAX_ROOMS


# ---------------------------------------------------------------------------
# AddDepartmentRequest
# ---------------------------------------------------------------------------
class TestAddDepartmentRequest:
    def test_valid(self):
        req = AddDepartmentRequest(
            symposium_id=UUID1,
            department_name="Biology",
            department_head_name="Smith",
            email="smith@hamilton.edu",
        )
        assert req.email == "smith@hamilton.edu"

    def test_empty_dept_name_raises(self):
        with pytest.raises(ValidationError):
            AddDepartmentRequest(
                symposium_id=UUID1,
                department_name="",
                department_head_name="Smith",
                email="s@hamilton.edu",
            )

    def test_empty_head_name_raises(self):
        with pytest.raises(ValidationError):
            AddDepartmentRequest(
                symposium_id=UUID1,
                department_name="Bio",
                department_head_name="  ",
                email="s@hamilton.edu",
            )

    def test_non_hamilton_email_raises(self):
        with pytest.raises(ValidationError, match="hamilton.edu"):
            AddDepartmentRequest(
                symposium_id=UUID1,
                department_name="Bio",
                department_head_name="Smith",
                email="smith@gmail.com",
            )

    def test_email_normalized_lowercase(self):
        req = AddDepartmentRequest(
            symposium_id=UUID1,
            department_name="Bio",
            department_head_name="Smith",
            email="  SMITH@Hamilton.EDU  ",
        )
        assert req.email == "smith@hamilton.edu"


# ---------------------------------------------------------------------------
# AddClassRequest
# ---------------------------------------------------------------------------
class TestAddClassRequest:
    def test_valid(self):
        req = AddClassRequest(
            name="BIO101",
            department_id=UUID1,
            professors=[{"name": "Smith", "email": "s@hamilton.edu"}],
        )
        assert req.name == "BIO101"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            AddClassRequest(name=" ", department_id=UUID1, professors=[])


# ---------------------------------------------------------------------------
# StudentInit
# ---------------------------------------------------------------------------
class TestStudentInit:
    def test_valid(self):
        s = StudentInit(name="Alice", email="alice@hamilton.edu")
        assert s.name == "Alice"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            StudentInit(name="  ", email="a@hamilton.edu")

    def test_bad_email_raises(self):
        with pytest.raises(ValidationError, match="hamilton"):
            StudentInit(name="Alice", email="alice@example.com")


# ---------------------------------------------------------------------------
# AddStudentsRequest
# ---------------------------------------------------------------------------
class TestAddStudentsRequest:
    def test_valid(self):
        req = AddStudentsRequest(
            class_id=UUID1,
            students=[{"name": "Bob", "email": "bob@hamilton.edu"}],
        )
        assert len(req.students) == 1


# ---------------------------------------------------------------------------
# AddPresentationRequest
# ---------------------------------------------------------------------------
class TestAddPresentationRequest:
    def test_valid(self):
        req = AddPresentationRequest(
            title="My Talk",
            class_id=UUID1,
            minutes=20,
            presenting_students=[UUID2],
        )
        assert req.minutes == 20

    def test_empty_title_raises(self):
        with pytest.raises(ValidationError):
            AddPresentationRequest(
                title="", class_id=UUID1, minutes=10, presenting_students=[]
            )

    def test_minutes_too_low(self):
        with pytest.raises(ValidationError):
            AddPresentationRequest(
                title="T", class_id=UUID1, minutes=0, presenting_students=[]
            )

    def test_minutes_too_high(self):
        with pytest.raises(ValidationError):
            AddPresentationRequest(
                title="T", class_id=UUID1, minutes=MAX_TIME + 1, presenting_students=[]
            )

    def test_too_many_presenting_students(self):
        ids = [uuid4() for _ in range(MAX_PRESENTING_STUDENTS + 1)]
        with pytest.raises(ValidationError, match="present"):
            AddPresentationRequest(
                title="T", class_id=UUID1, minutes=10, presenting_students=ids
            )


# ---------------------------------------------------------------------------
# AddReqRequest
# ---------------------------------------------------------------------------
class TestAddReqRequest:
    def test_valid(self):
        req = AddReqRequest(
            name="Prof X", email="profx@hamilton.edu", student_id=UUID1
        )
        assert req.name == "Prof X"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            AddReqRequest(name="  ", email="a@hamilton.edu", student_id=UUID1)

    def test_bad_email_raises(self):
        with pytest.raises(ValidationError):
            AddReqRequest(name="X", email="x@gmail.com", student_id=UUID1)


# ---------------------------------------------------------------------------
# Update schemas – must have at least one update field
# ---------------------------------------------------------------------------
class TestUpdateStudentRequest:
    def test_valid(self):
        req = UpdateStudentRequest(student_id=UUID1, name="New Name")
        assert req.name == "New Name"

    def test_no_updates_raises(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdateStudentRequest(student_id=UUID1)

    def test_email_validation(self):
        with pytest.raises(ValidationError, match="hamilton"):
            UpdateStudentRequest(
                student_id=UUID1, email="bad@gmail.com"
            )


class TestUpdateProfessorRequest:
    def test_valid(self):
        req = UpdateProfessorRequest(professor_id=UUID1, name="Dr. New")
        assert req.name == "Dr. New"

    def test_no_updates_raises(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdateProfessorRequest(professor_id=UUID1)


class TestUpdateClassRequest:
    def test_valid(self):
        req = UpdateClassRequest(class_id=UUID1, name="NewClass")
        assert req.name == "NewClass"

    def test_no_updates_raises(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdateClassRequest(class_id=UUID1)


class TestUpdateSymposiumRequest:
    def test_valid(self):
        req = UpdateSymposiumRequest(symposium_id=UUID1, symposium_name="New")
        assert req.symposium_name == "New"

    def test_no_updates_raises(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdateSymposiumRequest(symposium_id=UUID1)

    def test_rooms_over_max(self):
        with pytest.raises(ValidationError, match="rooms"):
            UpdateSymposiumRequest(
                symposium_id=UUID1, rooms_available=MAX_ROOMS + 1
            )


class TestUpdateDepartmentRequest:
    def test_valid(self):
        req = UpdateDepartmentRequest(
            department_id=UUID1,
            department_name="Physics",
            department_head_name="Jones",
            email="jones@hamilton.edu",
        )
        assert req.department_name == "Physics"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            UpdateDepartmentRequest(
                department_id=UUID1,
                department_name="",
                department_head_name="J",
                email="j@hamilton.edu",
            )


class TestUpdatePresentationRequest:
    def test_valid_title_only(self):
        req = UpdatePresentationRequest(
            presentation_id=UUID1, title="New Title"
        )
        assert req.title == "New Title"

    def test_no_updates_raises(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdatePresentationRequest(presentation_id=UUID1)

    def test_minutes_out_of_range(self):
        with pytest.raises(ValidationError):
            UpdatePresentationRequest(
                presentation_id=UUID1, minutes=MAX_TIME + 1
            )

    def test_too_many_students(self):
        ids = [uuid4() for _ in range(MAX_PRESENTING_STUDENTS + 1)]
        with pytest.raises(ValidationError):
            UpdatePresentationRequest(
                presentation_id=UUID1, presenting_students=ids
            )


class TestUpdateTimeframesRequest:
    def test_valid(self):
        req = UpdateTimeframesRequest(
            linked_id=UUID1,
            timeframes=[{"start_time": NOW, "end_time": LATER}],
        )
        assert len(req.timeframes) == 1
