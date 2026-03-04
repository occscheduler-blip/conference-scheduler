"""Integration tests for all /api/events/* endpoints via FastAPI TestClient.

Every test uses the `client` fixture which patches the Supabase client.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


NOW = datetime.now(timezone.utc)
LATER = NOW + timedelta(hours=3)


# ===================================================================
# Health check (no auth)
# ===================================================================
class TestHealthCheck:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "environment" in body


# ===================================================================
# Auth enforcement
# ===================================================================
class TestAuth:
    def test_missing_key_returns_401(self, client):
        resp = client.get("/api/events/symposiums")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        resp = client.get(
            "/api/events/symposiums", headers={"X-API-Key": "wrong"}
        )
        assert resp.status_code == 401

    def test_valid_key_passes(self, client, api_headers):
        resp = client.get("/api/events/symposiums", headers=api_headers)
        assert resp.status_code == 200


# ===================================================================
# POST endpoints
# ===================================================================
class TestAddSymposium:
    def test_add_new_symposium(self, client, api_headers, mock_supabase):
        # No existing symposium
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        payload = {
            "symposium_name": "Spring Symposium",
            "rooms_available": 5,
            "timeframes": [
                {
                    "start_time": NOW.isoformat(),
                    "end_time": LATER.isoformat(),
                },
            ],
        }
        resp = client.post(
            "/api/events/add_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "saved"
        assert "symposium_id" in body
        assert "records_inserted" in body

    def test_add_symposium_with_existing_id_updates(self, client, api_headers, mock_supabase):
        sid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": str(sid)}], count=1
        )
        payload = {
            "symposium_id": str(sid),
            "symposium_name": "Updated",
            "rooms_available": 3,
            "timeframes": [],
        }
        resp = client.post(
            "/api/events/add_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["symposium_id"] == str(sid)

    def test_add_symposium_validation_error(self, client, api_headers):
        payload = {
            "symposium_name": "",
            "rooms_available": 5,
            "timeframes": [],
        }
        resp = client.post(
            "/api/events/add_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 422


class TestAddDepartment:
    def test_add_department(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "symposium_id": str(uuid4()),
            "department_name": "Biology",
            "department_head_name": "Dr. Smith",
            "email": "smith@hamilton.edu",
        }
        resp = client.post(
            "/api/events/add_department", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "Inserted"

    def test_bad_email_rejected(self, client, api_headers):
        payload = {
            "symposium_id": str(uuid4()),
            "department_name": "Bio",
            "department_head_name": "Smith",
            "email": "smith@gmail.com",
        }
        resp = client.post(
            "/api/events/add_department", json=payload, headers=api_headers
        )
        assert resp.status_code == 422


class TestAddClass:
    def test_add_class(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "name": "BIO 101",
            "department_id": str(uuid4()),
            "professors": [
                {"name": "Dr. A", "email": "a@hamilton.edu"},
                {"name": "Dr. B", "email": "b@hamilton.edu"},
            ],
        }
        resp = client.post(
            "/api/events/add_class", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "Inserted"
        assert len(body["professor_ids"]) == 2

    def test_empty_class_name_rejected(self, client, api_headers):
        payload = {
            "name": "",
            "department_id": str(uuid4()),
            "professors": [],
        }
        resp = client.post(
            "/api/events/add_class", json=payload, headers=api_headers
        )
        assert resp.status_code == 422


class TestAddStudents:
    def test_add_students(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "class_id": str(uuid4()),
            "students": [
                {"name": "Alice", "email": "alice@hamilton.edu"},
                {"name": "Bob", "email": "bob@hamilton.edu"},
            ],
        }
        resp = client.post(
            "/api/events/add_students", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "inserted"


class TestAddPresentation:
    def test_add_presentation(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "title": "My Research",
            "class_id": str(uuid4()),
            "minutes": 20,
            "presenting_students": [str(uuid4())],
        }
        resp = client.post(
            "/api/events/add_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "inserted"
        assert "presentation_id" in body

    def test_minutes_too_high_rejected(self, client, api_headers):
        payload = {
            "title": "Talk",
            "class_id": str(uuid4()),
            "minutes": 999,
            "presenting_students": [],
        }
        resp = client.post(
            "/api/events/add_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 422


class TestAddRequest:
    def test_add_request(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "name": "Prof Jones",
            "email": "jones@hamilton.edu",
            "student_id": str(uuid4()),
        }
        resp = client.post(
            "/api/events/add_request", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "inserted"


# ===================================================================
# GET endpoints
# ===================================================================
class TestGetSymposiums:
    def test_list_symposiums(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": str(uuid4()), "name": "Spring"}]
        )
        resp = client.get("/api/events/symposiums", headers=api_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "symposiums" in body


class TestGetSymposiumById:
    def test_found(self, client, api_headers, mock_supabase):
        sid = uuid4()

        def _table_side_effect(name):
            table = MagicMock()
            for m in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
                getattr(table, m).return_value = table
            if name == "symposiums":
                table.execute.return_value = SimpleNamespace(
                    data=[{"id": str(sid), "name": "S"}]
                )
            elif name == "timeframes":
                table.execute.return_value = SimpleNamespace(data=[])
            else:
                table.execute.return_value = SimpleNamespace(data=[])
            return table

        mock_supabase.table.side_effect = _table_side_effect
        resp = client.get(
            f"/api/events/symposiums/{sid}", headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "symposium" in body
        assert "timeframes" in body

    def test_not_found(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get(
            f"/api/events/symposiums/{uuid4()}", headers=api_headers
        )
        assert resp.status_code == 404


class TestGetDepartments:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/departments", headers=api_headers)
        assert resp.status_code == 200

    def test_filtered(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get(
            f"/api/events/departments?symposium_id={uuid4()}", headers=api_headers
        )
        assert resp.status_code == 200


class TestGetClasses:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/classes", headers=api_headers)
        assert resp.status_code == 200


class TestGetStudents:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/students", headers=api_headers)
        assert resp.status_code == 200


class TestGetPresentations:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/presentations", headers=api_headers)
        assert resp.status_code == 200


class TestGetProfessors:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/professors", headers=api_headers)
        assert resp.status_code == 200


class TestGetTimeframes:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/timeframes", headers=api_headers)
        assert resp.status_code == 200


class TestGetRequests:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/requests", headers=api_headers)
        assert resp.status_code == 200


# ===================================================================
# PUT endpoints
# ===================================================================
class TestUpdateTimeframes:
    def test_update_timeframes(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        payload = {
            "linked_id": str(uuid4()),
            "timeframes": [
                {
                    "start_time": NOW.isoformat(),
                    "end_time": LATER.isoformat(),
                }
            ],
        }
        resp = client.put(
            "/api/events/update_timeframes", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "updated"


class TestUpdateStudent:
    def test_update_name(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {"student_id": str(uuid4()), "name": "New Name"}
        resp = client.put(
            "/api/events/update_student", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "name" in body["fields_updated"]

    def test_no_fields_rejected(self, client, api_headers):
        payload = {"student_id": str(uuid4())}
        resp = client.put(
            "/api/events/update_student", json=payload, headers=api_headers
        )
        assert resp.status_code == 422


class TestUpdateProfessor:
    def test_update_email(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "professor_id": str(uuid4()),
            "email": "new@hamilton.edu",
        }
        resp = client.put(
            "/api/events/update_professor", json=payload, headers=api_headers
        )
        assert resp.status_code == 200


class TestUpdateClass:
    def test_update_class_name(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {"class_id": str(uuid4()), "name": "BIO 202"}
        resp = client.put(
            "/api/events/update_class", json=payload, headers=api_headers
        )
        assert resp.status_code == 200


class TestUpdateDepartment:
    def test_update_department(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "department_id": str(uuid4()),
            "department_name": "Chemistry",
            "department_head_name": "Dr. Y",
            "email": "y@hamilton.edu",
        }
        resp = client.put(
            "/api/events/update_department", json=payload, headers=api_headers
        )
        assert resp.status_code == 200


class TestUpdateSymposium:
    def test_update_name(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "symposium_id": str(uuid4()),
            "symposium_name": "Fall Symposium",
        }
        resp = client.put(
            "/api/events/update_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "name" in body["fields_updated"]

    def test_update_rooms(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "symposium_id": str(uuid4()),
            "rooms_available": 10,
        }
        resp = client.put(
            "/api/events/update_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 200


class TestUpdatePresentation:
    def test_update_title(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[{}], count=1
        )
        payload = {
            "presentation_id": str(uuid4()),
            "title": "Updated Title",
        }
        resp = client.put(
            "/api/events/update_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["presenting_students_updated"] is False

    def test_update_presenting_students(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        payload = {
            "presentation_id": str(uuid4()),
            "presenting_students": [str(uuid4()), str(uuid4())],
        }
        resp = client.put(
            "/api/events/update_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["presenting_students_updated"] is True


# ===================================================================
# DELETE endpoints
# ===================================================================
class TestDeleteSymposium:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        sid = uuid4()
        resp = client.delete(
            f"/api/events/delete_symposium?symposium_id={sid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"


class TestDeleteDepartment:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        did = uuid4()
        resp = client.delete(
            f"/api/events/delete_department?department_id={did}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestDeleteClass:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        cid = uuid4()
        resp = client.delete(
            f"/api/events/delete_class?class_id={cid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestDeleteStudent:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        sid = uuid4()
        resp = client.delete(
            f"/api/events/delete_student?student_id={sid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestDeleteProfessor:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        pid = uuid4()
        resp = client.delete(
            f"/api/events/delete_professor?professor_id={pid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestDeletePresentation:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        pid = uuid4()
        resp = client.delete(
            f"/api/events/delete_presentation?presentation_id={pid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
