"""Integration tests for all /api/events/* endpoints via FastAPI TestClient.

Every test uses the `client` fixture which patches the Supabase client.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest


NOW = datetime.now(timezone.utc)
LATER = NOW + timedelta(hours=3)

# Realistic Supabase row shapes — IDs are strings, timestamps are ISO strings,
# nullable fields are None. These mirror what the real client returns.
_SYMP_ID = str(uuid4())
_DEPT_ID = str(uuid4())
_CLASS_ID = str(uuid4())
_PROF_ID = str(uuid4())
_STUDENT_ID = str(uuid4())
_PRES_ID = str(uuid4())
_TF_ID = str(uuid4())

SYMPOSIUM_ROW = {
    "id": _SYMP_ID,
    "name": "Spring Symposium",
    "rooms_available": 5,
    "created_at": "2026-03-06T12:00:00+00:00",
}
DEPARTMENT_ROW = {
    "id": _DEPT_ID,
    "department_name": "Biology",
    "department_head_name": "Dr. Smith",
    "email": "smith@hamilton.edu",
    "symposium_id": _SYMP_ID,
}
CLASS_ROW = {
    "id": _CLASS_ID,
    "name": "BIO 101",
    "department_id": _DEPT_ID,
}
PROFESSOR_ROW = {
    "id": _PROF_ID,
    "name": "Dr. A",
    "email": "a@hamilton.edu",
    "class_id": _CLASS_ID,
}
STUDENT_ROW = {
    "id": _STUDENT_ID,
    "name": "Alice",
    "email": "alice@hamilton.edu",
    "class_id": _CLASS_ID,
    "presentation_id": None,
}
PRESENTATION_ROW = {
    "id": _PRES_ID,
    "title": "My Research",
    "class_id": _CLASS_ID,
    "minutes": 20,
    "start_time": None,
    "end_time": None,
}
TIMEFRAME_ROW = {
    "id": _TF_ID,
    "linked_id": _SYMP_ID,
    "start_time": "2026-04-20T09:00:00+00:00",
    "end_time": "2026-04-20T12:00:00+00:00",
}


def _is_uuid(s: object) -> bool:
    """Return True if s is a valid UUID string."""
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


def _configure_mock(mock_supabase, data=None, count=None):
    """
    Override the table side_effect so every table call returns the given data.
    The conftest fixture uses side_effect=_table, so setting table.return_value
    has no effect — this helper replaces the side_effect instead.
    """
    def _table(name):
        table = MagicMock()
        for m in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
            getattr(table, m).return_value = table
        table.execute.return_value = SimpleNamespace(data=list(data or []), count=count)
        return table
    mock_supabase.table.side_effect = _table


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
        # Existence check returns empty; all insert/delete calls return count=1.
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
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
        assert _is_uuid(body["symposium_id"])
        assert body["name"] == "Spring Symposium"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])
        _assert_counts(body["records_updated"])
        _assert_counts(body["records_deleted"])

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
        assert body["name"] == "Updated"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

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
            data=[DEPARTMENT_ROW], count=1
        )
        symp_id = str(uuid4())
        payload = {
            "symposium_id": symp_id,
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
        assert _is_uuid(body["department_id"])
        assert _is_uuid(body["symposium_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

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
            data=[CLASS_ROW], count=1
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
        assert all(_is_uuid(pid) for pid in body["professor_ids"])
        assert _is_uuid(body["class_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

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
            data=[STUDENT_ROW, STUDENT_ROW], count=2
        )
        class_id = str(uuid4())
        payload = {
            "class_id": class_id,
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
        assert body["class_id"] == class_id
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])


class TestAddPresentation:
    def test_add_presentation(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[PRESENTATION_ROW], count=1
        )
        class_id = str(uuid4())
        payload = {
            "title": "My Research",
            "class_id": class_id,
            "minutes": 20,
            "presenting_students": [str(uuid4())],
        }
        resp = client.post(
            "/api/events/add_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "inserted"
        assert _is_uuid(body["presentation_id"])
        assert _is_uuid(body["class_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])

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
            data=[{"id": str(uuid4()), "name": "Prof Jones", "email": "jones@hamilton.edu", "student_id": _STUDENT_ID}],
            count=1,
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
        assert body["name"] == "Prof Jones"
        assert body["email"] == "jones@hamilton.edu"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])


# ===================================================================
# GET endpoints
# ===================================================================
class TestGetSymposiums:
    def test_list_symposiums(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[SYMPOSIUM_ROW])
        resp = client.get("/api/events/symposiums", headers=api_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "symposiums" in body
        assert len(body["symposiums"]) == 1
        row = body["symposiums"][0]
        assert row["id"] == _SYMP_ID
        assert row["name"] == "Spring Symposium"
        assert row["rooms_available"] == 5
        assert _is_uuid(row["id"])


class TestGetSymposiumById:
    def test_found(self, client, api_headers, mock_supabase):
        sid = uuid4()
        symp_row = {**SYMPOSIUM_ROW, "id": str(sid)}

        def _table_side_effect(name):
            table = MagicMock()
            for m in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
                getattr(table, m).return_value = table
            if name == "symposiums":
                table.execute.return_value = SimpleNamespace(data=[symp_row])
            elif name == "timeframes":
                table.execute.return_value = SimpleNamespace(data=[TIMEFRAME_ROW])
            else:
                table.execute.return_value = SimpleNamespace(data=[])
            return table

        mock_supabase.table.side_effect = _table_side_effect
        resp = client.get(f"/api/events/symposiums/{sid}", headers=api_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "symposium" in body
        assert "timeframes" in body
        assert body["symposium"]["id"] == str(sid)
        assert body["symposium"]["name"] == "Spring Symposium"
        assert body["symposium"]["rooms_available"] == 5
        assert len(body["timeframes"]) == 1
        tf = body["timeframes"][0]
        assert _is_uuid(tf["id"])
        assert "start_time" in tf and "end_time" in tf

    def test_not_found(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[])
        resp = client.get(
            f"/api/events/symposiums/{uuid4()}", headers=api_headers
        )
        assert resp.status_code == 404


class TestGetDepartments:
    def test_all(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[DEPARTMENT_ROW])
        resp = client.get("/api/events/departments", headers=api_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["departments"]) == 1
        assert _is_uuid(body["departments"][0]["id"])
        assert body["departments"][0]["department_name"] == "Biology"

    def test_filtered(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[DEPARTMENT_ROW])
        resp = client.get(
            f"/api/events/departments?symposium_id={uuid4()}", headers=api_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()["departments"]) == 1


class TestGetClasses:
    def test_all(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[CLASS_ROW])
        resp = client.get("/api/events/classes", headers=api_headers)
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert _is_uuid(rows[0]["id"])
        assert rows[0]["name"] == "BIO 101"


class TestGetStudents:
    def test_all(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[STUDENT_ROW])
        resp = client.get("/api/events/students", headers=api_headers)
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert _is_uuid(rows[0]["id"])
        assert rows[0]["presentation_id"] is None


class TestGetPresentations:
    def test_all(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        resp = client.get("/api/events/presentations", headers=api_headers)
        assert resp.status_code == 200


class TestGetProfessors:
    def test_all(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[PROFESSOR_ROW])
        resp = client.get("/api/events/professors", headers=api_headers)
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert _is_uuid(rows[0]["id"])
        assert rows[0]["email"] == "a@hamilton.edu"


class TestGetTimeframes:
    def test_all(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[TIMEFRAME_ROW])
        resp = client.get("/api/events/timeframes", headers=api_headers)
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert _is_uuid(rows[0]["id"])
        assert "start_time" in rows[0] and "end_time" in rows[0]


class TestGetRequests:
    def test_all(self, client, api_headers, mock_supabase):
        _configure_mock(mock_supabase, data=[{"id": str(uuid4()), "name": "Prof Jones", "email": "jones@hamilton.edu", "student_id": _STUDENT_ID}])
        resp = client.get("/api/events/requests", headers=api_headers)
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert _is_uuid(rows[0]["id"])
        assert _is_uuid(rows[0]["student_id"])


# ===================================================================
# PUT endpoints
# ===================================================================
class TestUpdateTimeframes:
    def test_update_timeframes(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[TIMEFRAME_ROW], count=1
        )
        linked_id = str(uuid4())
        payload = {
            "linked_id": linked_id,
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
        assert _is_uuid(body["linked_id"])
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_inserted"])
        _assert_counts(body["records_deleted"])


class TestUpdateStudent:
    def test_update_name(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[STUDENT_ROW], count=1
        )
        student_id = str(uuid4())
        payload = {
            "student_id": student_id,
            "name": "New Name",
            "email": "new@hamilton.edu",
            "class_id": str(uuid4()),
            "presentation_id": str(uuid4()),
        }
        resp = client.put(
            "/api/events/update_student", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["student_id"] == student_id
        assert "name" in body["fields_updated"]
        assert isinstance(body["fields_updated"], list)
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

    def test_no_fields_rejected(self, client, api_headers):
        payload = {"student_id": str(uuid4())}
        resp = client.put(
            "/api/events/update_student", json=payload, headers=api_headers
        )
        assert resp.status_code == 422


class TestUpdateProfessor:
    def test_update_email(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[PROFESSOR_ROW], count=1
        )
        prof_id = str(uuid4())
        payload = {
            "professor_id": prof_id,
            "name": "Dr. Smith",
            "email": "new@hamilton.edu",
            "class_id": str(uuid4()),
        }
        resp = client.put(
            "/api/events/update_professor", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["professor_id"] == prof_id
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])


class TestUpdateClass:
    def test_update_class_name(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[CLASS_ROW], count=1
        )
        class_id = str(uuid4())
        payload = {"class_id": class_id, "name": "BIO 202", "department_id": str(uuid4())}
        resp = client.put(
            "/api/events/update_class", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["class_id"] == class_id
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])


class TestUpdateDepartment:
    def test_update_department(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[DEPARTMENT_ROW], count=1
        )
        dept_id = str(uuid4())
        payload = {
            "department_id": dept_id,
            "department_name": "Chemistry",
            "department_head_name": "Dr. Y",
            "email": "y@hamilton.edu",
        }
        resp = client.put(
            "/api/events/update_department", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["department_id"] == dept_id
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])


class TestUpdateSymposium:
    def test_update_name(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[SYMPOSIUM_ROW], count=1
        )
        symp_id = str(uuid4())
        payload = {
            "symposium_id": symp_id,
            "symposium_name": "Fall Symposium",
            "rooms_available": 5,
        }
        resp = client.put(
            "/api/events/update_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["symposium_id"] == symp_id
        assert "name" in body["fields_updated"]
        assert isinstance(body["fields_updated"], list)
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])

    def test_update_rooms(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[SYMPOSIUM_ROW], count=1
        )
        payload = {
            "symposium_id": str(uuid4()),
            "symposium_name": "Fall Symposium",
            "rooms_available": 10,
        }
        resp = client.put(
            "/api/events/update_symposium", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0


class TestUpdatePresentation:
    def test_update_title(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[PRESENTATION_ROW], count=1
        )
        pres_id = str(uuid4())
        payload = {
            "presentation_id": pres_id,
            "title": "Updated Title",
            "class_id": str(uuid4()),
            "minutes": 20,
            "presenting_students": [],
        }
        resp = client.put(
            "/api/events/update_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["presentation_id"] == pres_id
        assert body["presenting_students_updated"] is True
        assert isinstance(body["fields_updated"], list)
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_updated"])
        _assert_counts(body["records_inserted"])
        _assert_counts(body["records_deleted"])

    def test_update_presenting_students(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[PRESENTATION_ROW], count=1
        )
        payload = {
            "presentation_id": str(uuid4()),
            "title": "My Talk",
            "class_id": str(uuid4()),
            "minutes": 15,
            "presenting_students": [str(uuid4()), str(uuid4())],
        }
        resp = client.put(
            "/api/events/update_presentation", json=payload, headers=api_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["presenting_students_updated"] is True
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0


# ===================================================================
# DELETE endpoints
# ===================================================================
class TestDeleteSymposium:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        sid = uuid4()
        resp = client.delete(
            f"/api/events/delete_symposium?symposium_id={sid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])


class TestDeleteDepartment:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        did = uuid4()
        resp = client.delete(
            f"/api/events/delete_department?department_id={did}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])


class TestDeleteClass:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        cid = uuid4()
        resp = client.delete(
            f"/api/events/delete_class?class_id={cid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])


class TestDeleteStudent:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        sid = uuid4()
        resp = client.delete(
            f"/api/events/delete_student?student_id={sid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])


class TestDeleteProfessor:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        pid = uuid4()
        resp = client.delete(
            f"/api/events/delete_professor?professor_id={pid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])


class TestDeletePresentation:
    def test_delete(self, client, api_headers, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        pid = uuid4()
        resp = client.delete(
            f"/api/events/delete_presentation?presentation_id={pid}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert isinstance(body["lines_edited"], int) and body["lines_edited"] >= 0
        _assert_counts(body["records_deleted"])
