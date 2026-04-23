"""Tests for supabase_io.read query functions against Docker Supabase."""

from uuid import uuid4, UUID

import pytest
from fastapi.testclient import TestClient

from app.supabase_io import read


from tests.builders import TF_1, seed_chain


def _seed_chain(client, h, db):
    """test_read variant: 1 student, with presentation + request. Returns `student_id`."""
    result = seed_chain(
        client, h, db,
        student_count=1,
        with_presentation=True,
        with_request=True,
    )
    return {
        "symposium_id": result["symposium_id"],
        "department_id": result["department_id"],
        "class_id": result["class_id"],
        "student_id": result["student_ids"][0],
    }


# ── Input validation (pure, no DB needed) ─────────────────────────────────


class TestInputValidation:
    def test_get_classes_invalid_type_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            read.get_classes(department_id="bad")

    def test_get_students_invalid_type_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            read.get_students(class_id="bad")

    def test_get_professors_invalid_type_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            read.get_professors(class_id=123)

    def test_get_timeframes_invalid_type_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            read.get_timeframes(linked_id=999)

    def test_get_requests_invalid_type_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            read.get_requests(student_id="not-a-uuid")


# ── Read functions against real data ──────────────────────────────────────


class TestGetSymposiums:
    def test_returns_symposium_rows(self, client, h, db):
        client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "Spring", "rooms_available": 5, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        result = read.get_symposiums()
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Spring"

    def test_empty_when_no_data(self, client, h, db):
        result = read.get_symposiums()
        assert result.data == []


class TestGetDepartments:
    def test_returns_all(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_departments()
        assert len(result.data) == 1
        assert result.data[0]["department_name"] == "CS"

    def test_with_symposium_filter(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_departments(symposium_id=UUID(ids["symposium_id"]))
        assert len(result.data) == 1

    def test_filter_no_match(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_departments(symposium_id=uuid4())
        assert result.data == []


class TestGetClasses:
    def test_returns_all(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_classes()
        assert len(result.data) == 1
        assert result.data[0]["name"] == "CS101"

    def test_with_department_filter(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_classes(department_id=UUID(ids["department_id"]))
        assert len(result.data) == 1

    def test_list_uuid_filter(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_classes(department_id=[UUID(ids["department_id"])])
        assert len(result.data) == 1


class TestGetStudents:
    def test_returns_students(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_students()
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Student 0"


class TestGetProfessors:
    def test_returns_professors(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_professors()
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Prof. Smith"


class TestGetTimeframes:
    def test_returns_all(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_timeframes()
        assert len(result.data) == 1

    def test_with_linked_id_filter(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_timeframes(linked_id=UUID(ids["symposium_id"]))
        assert len(result.data) == 1


class TestGetPresentingStudents:
    def test_returns_join_rows(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_presenting_students()
        assert len(result.data) == 1


class TestGetRequests:
    def test_returns_requests(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_requests()
        assert len(result.data) == 1

    def test_with_student_filter(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = read.get_requests(student_id=UUID(ids["student_id"]))
        assert len(result.data) == 1


class TestGetPresentations:
    def test_enriches_with_presenting_students(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_presentations()
        assert len(result.data) == 1
        assert "presenting_students" in result.data[0]
        assert len(result.data[0]["presenting_students"]) == 1
        assert result.data[0]["presenting_students"][0]["name"] == "Student 0"

    def test_empty_presentations(self, client, h, db):
        result = read.get_presentations()
        assert result.data == []
