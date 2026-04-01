"""Tests for supabase_io.read query functions against Docker Supabase."""

from uuid import uuid4, UUID

import pytest
from fastapi.testclient import TestClient

from app.supabase_io import read


# ── Shared helpers ─────────────────────────────────────────────────────────

TF_1 = {"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}


def _seed_chain(client: TestClient, h: dict[str, str], db) -> dict[str, str]:
    """Create symposium → department → class (+ professor) → students → presentation."""
    resp = client.post(
        "/api/events/add_symposium",
        json={"symposium_name": "Symp", "rooms_available": 1, "default_buffer": 0, "timeframes": [TF_1]},
        headers=h,
    )
    sym_id = resp.json()["symposium_id"]

    resp = client.post(
        "/api/events/add_department",
        json={
            "symposium_id": sym_id,
            "department_name": "CS",
            "department_head_name": "Dr. Head",
            "email": "head@hamilton.edu",
        },
        headers=h,
    )
    dept_id = resp.json()["department_id"]

    resp = client.post(
        "/api/events/add_class",
        json={
            "name": "CS101",
            "department_id": dept_id,
            "professors": [{"name": "Prof. A", "email": "profa@hamilton.edu"}],
        },
        headers=h,
    )
    class_id = resp.json()["class_id"]

    client.post(
        "/api/events/add_students",
        json={
            "class_id": class_id,
            "students": [{"name": "Alice", "email": "alice@hamilton.edu"}],
        },
        headers=h,
    )
    student_id = str(db.rows("students")[0]["id"])

    resp = client.post(
        "/api/events/add_presentation",
        json={
            "title": "My Talk",
            "class_id": class_id,
            "minutes": 15,
            "buffer": 0,
            "presenting_students": [student_id],
        },
        headers=h,
    )

    client.post(
        "/api/events/add_request",
        json={"name": "Prof. Pref", "email": "pref@hamilton.edu", "student_id": student_id},
        headers=h,
    )

    return {
        "symposium_id": sym_id,
        "department_id": dept_id,
        "class_id": class_id,
        "student_id": student_id,
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
        assert result.data[0]["name"] == "Alice"


class TestGetProfessors:
    def test_returns_professors(self, client, h, db):
        _seed_chain(client, h, db)
        result = read.get_professors()
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Prof. A"


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
        assert result.data[0]["presenting_students"][0]["name"] == "Alice"

    def test_empty_presentations(self, client, h, db):
        result = read.get_presentations()
        assert result.data == []
