"""Tests for supabase_io.delete cascade logic."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.supabase_io import delete


# ── Shared helpers ─────────────────────────────────────────────────────────

TF_1 = {"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}


def _seed_full(client: TestClient, h: dict[str, str], db) -> dict[str, str]:
    """Build: symposium → department → class (+ professor) → students → presentation + request."""
    resp = client.post(
        "/api/events/add_symposium",
        json={"symposium_name": "Symp", "rooms_available": 1, "timeframes": [TF_1]},
        headers=h,
    )
    sym_id = resp.json()["symposium_id"]

    resp = client.post(
        "/api/events/add_department",
        json={
            "symposium_id": sym_id,
            "department_name": "CS",
            "department_head_name": "Dr. H",
            "email": "h@hamilton.edu",
        },
        headers=h,
    )
    dept_id = resp.json()["department_id"]

    resp = client.post(
        "/api/events/add_class",
        json={
            "name": "CS101",
            "department_id": dept_id,
            "professors": [{"name": "Prof A", "email": "a@hamilton.edu"}],
        },
        headers=h,
    )
    class_id = resp.json()["class_id"]

    client.post(
        "/api/events/add_students",
        json={
            "class_id": class_id,
            "students": [
                {"name": "Stu 1", "email": "s1@hamilton.edu"},
                {"name": "Stu 2", "email": "s2@hamilton.edu"},
            ],
        },
        headers=h,
    )
    student_ids = [str(r["id"]) for r in db.rows("students")]

    resp = client.post(
        "/api/events/add_presentation",
        json={
            "title": "Talk",
            "class_id": class_id,
            "minutes": 15,
            "presenting_students": student_ids,
        },
        headers=h,
    )
    pres_id = resp.json()["presentation_id"]

    client.post(
        "/api/events/add_request",
        json={"name": "Prof P", "email": "p@hamilton.edu", "student_id": student_ids[0]},
        headers=h,
    )

    prof_id = str(db.rows("professors")[0]["id"])

    return {
        "symposium_id": sym_id,
        "department_id": dept_id,
        "class_id": class_id,
        "professor_id": prof_id,
        "student_ids": student_ids,
        "presentation_id": pres_id,
    }


# ── Pure unit tests (no DB needed) ────────────────────────────────────────


class TestRowsAffectedDelete:
    """Test the local _rows_affected helper in delete module."""

    def test_dict_count(self):
        assert delete._rows_affected({"count": 3}) == 3

    def test_object_data_list(self):
        assert delete._rows_affected(SimpleNamespace(data=[1, 2])) == 2

    def test_fallback(self):
        assert delete._rows_affected(SimpleNamespace(), fallback=9) == 9


class TestMergeCounts:
    def test_merge_into_empty(self):
        target: dict[str, int] = {}
        delete._merge_counts(target, {"a": 1, "b": 2})
        assert target == {"a": 1, "b": 2}

    def test_merge_accumulates(self):
        target = {"a": 3}
        delete._merge_counts(target, {"a": 2, "b": 1})
        assert target == {"a": 5, "b": 1}

    def test_none_source_is_noop(self):
        target = {"a": 1}
        delete._merge_counts(target, None)
        assert target == {"a": 1}

    def test_negative_values_ignored(self):
        target: dict[str, int] = {}
        delete._merge_counts(target, {"a": -1, "b": 5})
        assert target == {"b": 5}


class TestSafeCount:
    def test_positive_int(self):
        assert delete._safe_count(5) == 5

    def test_zero(self):
        assert delete._safe_count(0) == 0

    def test_negative(self):
        assert delete._safe_count(-1) == 0

    def test_non_int(self):
        assert delete._safe_count("bad") == 0


# ── Docker Supabase cascade delete tests ──────────────────────────────────


class TestDeleteTimeframes:
    def test_deletes_timeframes_for_linked_id(self, client, h, db):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "timeframes": [TF_1]},
            headers=h,
        )
        sym_id = resp.json()["symposium_id"]
        assert db.count("timeframes") == 1

        result = delete.delete_timeframes(UUID(sym_id))
        assert result >= 1
        assert db.count("timeframes") == 0


class TestDeleteStudent:
    def test_returns_count_dict_and_removes_student(self, client, h, db):
        ids = _seed_full(client, h, db)
        student_id = UUID(ids["student_ids"][0])

        result = delete.delete_student(student_id)
        assert isinstance(result, dict)
        assert "students" in result
        assert "presenting_students" in result
        assert "requests" in result
        assert "timeframes" in result
        for val in result.values():
            assert isinstance(val, int) and val >= 0
        assert db.count("students") == 1  # one of two removed


class TestDeleteProfessor:
    def test_returns_count_dict_and_removes_professor(self, client, h, db):
        ids = _seed_full(client, h, db)

        result = delete.delete_professor(UUID(ids["professor_id"]))
        assert isinstance(result, dict)
        assert "professors" in result
        assert db.count("professors") == 0


class TestDeletePresentation:
    def test_returns_count_dict_and_removes_presentation(self, client, h, db):
        ids = _seed_full(client, h, db)

        result = delete.delete_presentation(UUID(ids["presentation_id"]))
        assert isinstance(result, dict)
        assert "presentations" in result
        assert "presenting_students" in result
        assert db.count("presentations") == 0
        assert db.count("presenting_students") == 0


class TestDeleteClass:
    def test_cascade_removes_class_and_children(self, client, h, db):
        ids = _seed_full(client, h, db)

        result = delete.delete_class(UUID(ids["class_id"]))
        assert isinstance(result, dict)
        assert "classes" in result
        assert db.count("classes") == 0
        assert db.count("professors") == 0
        assert db.count("students") == 0
        assert db.count("presentations") == 0

    def test_list_dispatches_to_multiple(self, client, h, db):
        """Passing a list of UUIDs deletes all of them."""
        ids = _seed_full(client, h, db)
        result = delete.delete_class([UUID(ids["class_id"])])
        assert isinstance(result, dict)
        assert db.count("classes") == 0


class TestDeleteDepartment:
    def test_cascade_removes_department_and_children(self, client, h, db):
        ids = _seed_full(client, h, db)

        result = delete.delete_department(UUID(ids["department_id"]))
        assert isinstance(result, dict)
        assert "departments" in result
        assert db.count("departments") == 0
        assert db.count("classes") == 0

    def test_list_dispatches(self, client, h, db):
        ids = _seed_full(client, h, db)
        result = delete.delete_department([UUID(ids["department_id"])])
        assert isinstance(result, dict)
        assert db.count("departments") == 0


class TestDeleteSymposium:
    def test_cascade_removes_everything(self, client, h, db):
        ids = _seed_full(client, h, db)

        result = delete.delete_symposium(UUID(ids["symposium_id"]))
        assert isinstance(result, dict)
        assert "timeframes" in result
        assert db.count("symposiums") == 0
        assert db.count("departments") == 0
        assert db.count("classes") == 0
        assert db.count("timeframes") == 0
