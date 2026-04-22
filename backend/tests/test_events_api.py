"""Validation and response-shape tests for /api/events/* (Docker Supabase).

These complement test_api.py by focusing on:
  - 422 validation errors for bad input
  - Response body structure (lines_edited, records_*, fields_updated)
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


# ── Shared helpers ─────────────────────────────────────────────────────────

TF_1 = {"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}
TF_2 = {"start_time": "2026-04-21T13:00:00Z", "end_time": "2026-04-21T16:00:00Z"}


def _is_uuid(s: object) -> bool:
    try:
        UUID(str(s))
        return True
    except (ValueError, AttributeError):
        return False


def _assert_counts(d: dict) -> None:
    """Assert every value in a records_* dict is a non-negative integer."""
    for key, val in d.items():
        assert isinstance(val, int), f"{key} count is not int: {val!r}"
        assert val >= 0, f"{key} count is negative: {val}"


def _seed_chain(client: TestClient, h: dict[str, str], db) -> dict[str, str]:
    """Create symposium → department → class (+ professor) → students."""
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
            "professors": [{"name": "Prof A", "email": "profa@hamilton.edu"}],
        },
        headers=h,
    )
    class_id = resp.json()["class_id"]
    prof_ids = resp.json()["professor_ids"]

    client.post(
        "/api/events/add_students",
        json={
            "class_id": class_id,
            "students": [
                {"name": "Alice", "email": "alice@hamilton.edu"},
                {"name": "Bob", "email": "bob@hamilton.edu"},
            ],
        },
        headers=h,
    )
    student_ids = [str(r["id"]) for r in db.rows("students")]

    return {
        "symposium_id": sym_id,
        "department_id": dept_id,
        "class_id": class_id,
        "professor_id": prof_ids[0],
        "student_ids": student_ids,
    }


# ── Validation error tests (422) ──────────────────────────────────────────


class TestValidation:
    def test_empty_symposium_name_rejected(self, client, h):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "", "rooms_available": 5, "default_buffer": 0, "timeframes": []},
            headers=h,
        )
        assert resp.status_code == 422

    def test_bad_email_rejected(self, client, h):
        resp = client.post(
            "/api/events/add_department",
            json={
                "symposium_id": str(uuid4()),
                "department_name": "Bio",
                "department_head_name": "Smith",
                "email": "smith@gmail.com",
            },
            headers=h,
        )
        assert resp.status_code == 422

    def test_empty_class_name_rejected(self, client, h):
        resp = client.post(
            "/api/events/add_class",
            json={"name": "", "department_id": str(uuid4()), "professors": []},
            headers=h,
        )
        assert resp.status_code == 422

    def test_presentation_minutes_too_high_rejected(self, client, h):
        resp = client.post(
            "/api/events/add_presentation",
            json={
                "title": "Talk",
                "class_id": str(uuid4()),
                "minutes": 999,
                "buffer": 0,
                "presenting_students": [],
            },
            headers=h,
        )
        assert resp.status_code == 422

    def test_update_student_no_fields_rejected(self, client, h):
        resp = client.put(
            "/api/events/update_student",
            json={"student_id": str(uuid4())},
            headers=h,
        )
        assert resp.status_code == 422


# ── Response shape: POST endpoints ────────────────────────────────────────


class TestPostResponseShapes:
    def test_add_symposium_shape(self, client, h):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "Spring", "rooms_available": 5, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "created"
        assert _is_uuid(body["symposium_id"])
        assert body["name"] == "Spring"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

    def test_add_department_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        # We already created a department in seed, let's verify the shape from a fresh one
        resp = client.post(
            "/api/events/add_department",
            json={
                "symposium_id": ids["symposium_id"],
                "department_name": "Bio",
                "department_head_name": "Dr. B",
                "email": "bio@hamilton.edu",
            },
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "Inserted"
        assert _is_uuid(body["department_id"])
        assert _is_uuid(body["symposium_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

    def test_add_class_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.post(
            "/api/events/add_class",
            json={
                "name": "CS201",
                "department_id": ids["department_id"],
                "professors": [
                    {"name": "Dr. X", "email": "x@hamilton.edu"},
                    {"name": "Dr. Y", "email": "y@hamilton.edu"},
                ],
            },
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "Inserted"
        assert _is_uuid(body["class_id"])
        assert len(body["professor_ids"]) == 2
        assert all(_is_uuid(pid) for pid in body["professor_ids"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

    def test_add_students_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.post(
            "/api/events/add_students",
            json={
                "class_id": ids["class_id"],
                "students": [{"name": "Carol", "email": "carol@hamilton.edu"}],
            },
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "inserted"
        assert body["class_id"] == ids["class_id"]
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

    def test_add_presentation_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.post(
            "/api/events/add_presentation",
            json={
                "title": "My Talk",
                "class_id": ids["class_id"],
                "minutes": 20,
                "buffer": 0,
                "presenting_students": ids["student_ids"],
            },
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "inserted"
        assert _is_uuid(body["presentation_id"])
        assert _is_uuid(body["class_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

    def test_add_request_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.post(
            "/api/events/add_request",
            json={
                "name": "Prof Jones",
                "email": "jones@hamilton.edu",
                "student_id": ids["student_ids"][0],
            },
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "inserted"
        assert body["name"] == "Prof Jones"
        assert body["email"] == "jones@hamilton.edu"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])


# ── Response shape: PUT endpoints ─────────────────────────────────────────


class TestPutResponseShapes:
    def test_update_symposium_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.put(
            "/api/events/update_symposium",
            json={
                "symposium_id": ids["symposium_id"],
                "symposium_name": "Fall",
                "rooms_available": 10,
                "default_buffer": 0,
                "timeframes": [TF_1],
            },
            headers=h,
        )
        body = resp.json()
        assert body["symposium_id"] == ids["symposium_id"]
        assert "name" in body["fields_updated"]
        assert isinstance(body["fields_updated"], list)
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])
        _assert_counts(body["records_deleted"])
        _assert_counts(body["records_inserted"])

    def test_update_department_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.put(
            "/api/events/update_department",
            json={
                "department_id": ids["department_id"],
                "department_name": "Math",
                "department_head_name": "Dr. M",
                "email": "m@hamilton.edu",
            },
            headers=h,
        )
        body = resp.json()
        assert body["department_id"] == ids["department_id"]
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

    def test_update_class_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.put(
            "/api/events/update_class",
            json={
                "class_id": ids["class_id"],
                "name": "CS999",
                "department_id": ids["department_id"],
            },
            headers=h,
        )
        body = resp.json()
        assert body["class_id"] == ids["class_id"]
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

    def test_update_student_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        # Need a presentation for the student
        pres_resp = client.post(
            "/api/events/add_presentation",
            json={
                "title": "Talk",
                "class_id": ids["class_id"],
                "minutes": 15,
                "buffer": 0,
                "presenting_students": ids["student_ids"],
            },
            headers=h,
        )
        pres_id = pres_resp.json()["presentation_id"]

        resp = client.put(
            "/api/events/update_student",
            json={
                "student_id": ids["student_ids"][0],
                "name": "New Name",
                "email": "new@hamilton.edu",
                "class_id": ids["class_id"],
                "presentation_id": pres_id,
            },
            headers=h,
        )
        body = resp.json()
        assert body["student_id"] == ids["student_ids"][0]
        assert "name" in body["fields_updated"]
        assert isinstance(body["fields_updated"], list)
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

    def test_update_professor_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.put(
            "/api/events/update_professor",
            json={
                "professor_id": ids["professor_id"],
                "name": "Dr. New",
                "email": "new@hamilton.edu",
                "class_id": ids["class_id"],
            },
            headers=h,
        )
        body = resp.json()
        assert body["professor_id"] == ids["professor_id"]
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

    def test_update_timeframes_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.put(
            "/api/events/update_timeframes",
            json={"linked_id": ids["symposium_id"], "timeframes": [TF_2]},
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "updated"
        assert _is_uuid(body["linked_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])
        _assert_counts(body["records_deleted"])

    def test_update_presentation_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        pres_resp = client.post(
            "/api/events/add_presentation",
            json={
                "title": "Talk",
                "class_id": ids["class_id"],
                "minutes": 15,
                "buffer": 0,
                "presenting_students": ids["student_ids"],
            },
            headers=h,
        )
        pres_id = pres_resp.json()["presentation_id"]

        resp = client.put(
            "/api/events/update_presentation",
            json={
                "presentation_id": pres_id,
                "title": "Updated Talk",
                "class_id": ids["class_id"],
                "minutes": 20,
                "buffer": 0,
                "presenting_students": [ids["student_ids"][0]],
            },
            headers=h,
        )
        body = resp.json()
        assert body["presentation_id"] == pres_id
        assert body["presenting_students_updated"] is True
        assert isinstance(body["fields_updated"], list)
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])
        _assert_counts(body["records_inserted"])
        _assert_counts(body["records_deleted"])


# ── Response shape: DELETE endpoints ──────────────────────────────────────


class TestDeleteResponseShapes:
    def test_delete_symposium_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.delete(
            f"/api/events/delete_symposium?symposium_id={ids['symposium_id']}",
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])

    def test_delete_class_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.delete(
            f"/api/events/delete_class?class_id={ids['class_id']}", headers=h
        )
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])
        assert body["records_deleted"].get("classes", 0) >= 1

    def test_delete_student_shape(self, client, h, db):
        ids = _seed_chain(client, h, db)
        resp = client.delete(
            f"/api/events/delete_student?student_id={ids['student_ids'][0]}",
            headers=h,
        )
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])
