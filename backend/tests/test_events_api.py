from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.routers import events


@pytest.fixture
def client():
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_endpoint_returns_environment(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "environment" in body


def test_add_symposium_inserts_timeframes_and_symposium(client, monkeypatch):
    symposium_id = str(uuid4())
    write_calls = []

    class SymposiumQueryStub:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def update(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class SupabaseStub:
        def table(self, _name):
            return SymposiumQueryStub()

    def fake_insert(table_name, payload):
        write_calls.append((table_name, payload))
        return SimpleNamespace(data=payload)

    monkeypatch.setattr(events, "supabase", SupabaseStub())
    monkeypatch.setattr(events.delete, "delete_timeframes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(events.write, "insert", fake_insert)
    response = client.post(
        "/api/events/add_symposium",
        json={
            "symposium_id": symposium_id,
            "symposium_name": "Spring Symposium",
            "rooms_available": 3,
            "timeframes": [
                {
                    "start_time": "2026-04-20T09:00:00Z",
                    "end_time": "2026-04-20T10:00:00Z",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "saved"
    assert body["symposium_id"] == symposium_id
    assert body["records_inserted"] == {"symposiums": 1, "timeframes": 1}
    assert [name for name, _payload in write_calls] == ["symposiums", "timeframes"]


def test_add_symposium_returns_500_on_unexpected_write_error(client, monkeypatch):
    class SymposiumQueryStub:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def update(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class SupabaseStub:
        def table(self, _name):
            return SymposiumQueryStub()

    monkeypatch.setattr(events, "supabase", SupabaseStub())
    monkeypatch.setattr(events.delete, "delete_timeframes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        events.write,
        "insert",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    response = client.post(
        "/api/events/add_symposium",
        json={
            "symposium_name": "Spring Symposium",
            "rooms_available": 3,
            "timeframes": [
                {
                    "start_time": "2026-04-20T09:00:00Z",
                    "end_time": "2026-04-20T10:00:00Z",
                }
            ],
        },
    )
    assert response.status_code == 500
    assert "Failed to validate symposium payload" in response.json()["detail"]


def test_add_students_inserts_all_students(client, monkeypatch):
    class_id = str(uuid4())
    inserted = {}

    def fake_insert(table_name, payload):
        inserted["table"] = table_name
        inserted["payload"] = payload
        return SimpleNamespace(data=payload)

    monkeypatch.setattr(events.write, "insert", fake_insert)
    response = client.post(
        "/api/events/add_students",
        json={
            "class_id": class_id,
            "students": [
                {"name": "A", "email": "a@hamilton.edu"},
                {"name": "B", "email": "b@hamilton.edu"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["records_inserted"]["students"] == 2
    assert inserted["table"] == "students"
    assert len(inserted["payload"]) == 2


def test_update_student_updates_requested_fields(client, monkeypatch):
    calls = []

    class QueryStub:
        def __init__(self, table_name):
            self.table_name = table_name

        def update(self, payload):
            calls.append((self.table_name, "update", payload))
            return self

        def eq(self, field, value):
            calls.append((self.table_name, "eq", field, value))
            return self

        def execute(self):
            return {"data": []}

    class SupabaseStub:
        def table(self, table_name):
            return QueryStub(table_name)

    student_id = uuid4()
    monkeypatch.setattr(events, "supabase", SupabaseStub())
    response = client.put(
        "/api/events/update_student",
        json={
            "student_id": str(student_id),
            "name": "Updated Student",
            "email": "updated@hamilton.edu",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
    assert ("students", "update", {"name": "Updated Student", "email": "updated@hamilton.edu"}) in calls


def test_update_symposium_maps_symposium_name_to_name(client, monkeypatch):
    calls = []

    class QueryStub:
        def __init__(self, table_name):
            self.table_name = table_name

        def update(self, payload):
            calls.append((self.table_name, "update", payload))
            return self

        def eq(self, field, value):
            calls.append((self.table_name, "eq", field, value))
            return self

        def execute(self):
            return {"data": []}

    class SupabaseStub:
        def table(self, table_name):
            return QueryStub(table_name)

    symposium_id = uuid4()
    monkeypatch.setattr(events, "supabase", SupabaseStub())
    response = client.put(
        "/api/events/update_symposium",
        json={"symposium_id": str(symposium_id), "symposium_name": "Renamed"},
    )

    assert response.status_code == 200
    assert ("symposiums", "update", {"name": "Renamed"}) in calls


def test_update_class_returns_400_when_update_fails(client, monkeypatch):
    class QueryStub:
        def update(self, _payload):
            return self

        def eq(self, _field, _value):
            return self

        def execute(self):
            raise RuntimeError("boom")

    class SupabaseStub:
        def table(self, _table_name):
            return QueryStub()

    monkeypatch.setattr(events, "supabase", SupabaseStub())
    response = client.put(
        "/api/events/update_class",
        json={"class_id": str(uuid4()), "name": "Updated class"},
    )

    assert response.status_code == 400
    assert "Failed to update class" in response.json()["detail"]


def test_update_presentation_replaces_presenting_students(client, monkeypatch):
    calls = []
    inserts = []

    class QueryStub:
        def __init__(self, table_name):
            self.table_name = table_name

        def update(self, payload):
            calls.append((self.table_name, "update", payload))
            return self

        def delete(self):
            calls.append((self.table_name, "delete"))
            return self

        def eq(self, field, value):
            calls.append((self.table_name, "eq", field, value))
            return self

        def execute(self):
            return {"data": []}

    class SupabaseStub:
        def table(self, table_name):
            return QueryStub(table_name)

    def fake_insert(table_name, payload):
        inserts.append((table_name, payload))
        return SimpleNamespace(data=payload)

    presentation_id = uuid4()
    monkeypatch.setattr(events, "supabase", SupabaseStub())
    monkeypatch.setattr(events.write, "insert", fake_insert)
    response = client.put(
        "/api/events/update_presentation",
        json={
            "presentation_id": str(presentation_id),
            "title": "Updated Title",
            "presenting_students": [str(uuid4()), str(uuid4())],
        },
    )

    assert response.status_code == 200
    assert ("presentations", "update", {"title": "Updated Title"}) in calls
    assert ("presenting_students", "delete") in calls
    assert inserts and inserts[0][0] == "presenting_students"
    assert len(inserts[0][1]) == 2


def test_get_departments_forwards_query_param(client, monkeypatch):
    symposium_id = uuid4()
    captured = {"value": None}

    def fake_get_departments(symposium_id=None):
        captured["value"] = symposium_id
        return {"data": []}

    monkeypatch.setattr(events.read, "get_departments", fake_get_departments)

    response = client.get(f"/api/events/departments?symposium_id={symposium_id}")

    assert response.status_code == 200
    assert captured["value"] == symposium_id


def test_get_classes_returns_400_when_read_layer_fails(client, monkeypatch):
    monkeypatch.setattr(
        events.read,
        "get_classes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.get("/api/events/classes")
    assert response.status_code == 400
    assert "Failed to get classes" in response.json()["detail"]


def test_delete_symposium_calls_delete_layer(client, monkeypatch):
    symposium_id = uuid4()
    called = {"value": None}

    def fake_delete_symposium(value):
        called["value"] = value

    monkeypatch.setattr(events.delete, "delete_symposium", fake_delete_symposium)

    response = client.delete(f"/api/events/delete_symposium?symposium_id={symposium_id}")

    assert response.status_code == 200
    assert called["value"] == symposium_id
    assert response.json()["status"] == "deleted"


def test_delete_department_calls_delete_layer(client, monkeypatch):
    department_id = uuid4()
    called = {"value": None}

    def fake_delete_department(value):
        called["value"] = value

    monkeypatch.setattr(events.delete, "delete_department", fake_delete_department)

    response = client.delete(
        f"/api/events/delete_department?department_id={department_id}"
    )

    assert response.status_code == 200
    assert called["value"] == department_id
    assert response.json() == {"status": "deleted", "records_deleted": {"departments": 1}}


def test_delete_department_returns_400_when_delete_layer_fails(client, monkeypatch):
    monkeypatch.setattr(
        events.delete,
        "delete_department",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.delete(f"/api/events/delete_department?department_id={uuid4()}")

    assert response.status_code == 400
    assert "Failed to delete department" in response.json()["detail"]


def test_delete_class_calls_delete_layer(client, monkeypatch):
    class_id = uuid4()
    called = {"value": None}

    def fake_delete_class(value):
        called["value"] = value

    monkeypatch.setattr(events.delete, "delete_class", fake_delete_class)

    response = client.delete(f"/api/events/delete_class?class_id={class_id}")

    assert response.status_code == 200
    assert called["value"] == class_id
    assert response.json() == {"status": "deleted", "records_deleted": {"classes": 1}}


def test_delete_class_returns_400_when_delete_layer_fails(client, monkeypatch):
    monkeypatch.setattr(
        events.delete,
        "delete_class",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.delete(f"/api/events/delete_class?class_id={uuid4()}")

    assert response.status_code == 400
    assert "Failed to delete class" in response.json()["detail"]


def test_delete_student_calls_delete_layer(client, monkeypatch):
    student_id = uuid4()
    called = {"value": None}

    def fake_delete_student(value):
        called["value"] = value

    monkeypatch.setattr(events.delete, "delete_student", fake_delete_student)

    response = client.delete(f"/api/events/delete_student?student_id={student_id}")

    assert response.status_code == 200
    assert called["value"] == student_id
    assert response.json() == {"status": "deleted", "records_deleted": {"students": 1}}


def test_delete_student_returns_400_when_delete_layer_fails(client, monkeypatch):
    monkeypatch.setattr(
        events.delete,
        "delete_student",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.delete(f"/api/events/delete_student?student_id={uuid4()}")

    assert response.status_code == 400
    assert "Failed to delete student" in response.json()["detail"]


def test_delete_professor_calls_delete_layer(client, monkeypatch):
    professor_id = uuid4()
    called = {"value": None}

    def fake_delete_professor(value):
        called["value"] = value

    monkeypatch.setattr(events.delete, "delete_professor", fake_delete_professor)

    response = client.delete(f"/api/events/delete_professor?professor_id={professor_id}")

    assert response.status_code == 200
    assert called["value"] == professor_id
    assert response.json() == {"status": "deleted", "records_deleted": {"professors": 1}}


def test_delete_professor_returns_400_when_delete_layer_fails(client, monkeypatch):
    monkeypatch.setattr(
        events.delete,
        "delete_professor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.delete(f"/api/events/delete_professor?professor_id={uuid4()}")

    assert response.status_code == 400
    assert "Failed to delete professor" in response.json()["detail"]


def test_delete_presentation_calls_delete_layer(client, monkeypatch):
    presentation_id = uuid4()
    called = {"value": None}

    def fake_delete_presentation(value):
        called["value"] = value

    monkeypatch.setattr(events.delete, "delete_presentation", fake_delete_presentation)

    response = client.delete(
        f"/api/events/delete_presentation?presentation_id={presentation_id}"
    )

    assert response.status_code == 200
    assert called["value"] == presentation_id
    assert response.json() == {
        "status": "deleted",
        "records_deleted": {"presentations": 1},
    }


def test_delete_presentation_returns_400_when_delete_layer_fails(client, monkeypatch):
    monkeypatch.setattr(
        events.delete,
        "delete_presentation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.delete(f"/api/events/delete_presentation?presentation_id={uuid4()}")

    assert response.status_code == 400
    assert "Failed to delete presentation" in response.json()["detail"]


def test_protected_route_rejects_missing_api_key():
    no_key_client = TestClient(app)
    response = no_key_client.get("/api/events/symposiums")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key."


def test_protected_route_rejects_wrong_api_key():
    wrong_key_client = TestClient(app, headers={"X-API-Key": "wrong-key"})
    response = wrong_key_client.get("/api/events/symposiums")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key."


def test_protected_route_returns_500_if_backend_key_not_configured(monkeypatch):
    monkeypatch.setenv("BACKEND_API_KEY", "")
    get_settings.cache_clear()

    client = TestClient(app, headers={"X-API-Key": "anything"})
    response = client.get("/api/events/symposiums")

    assert response.status_code == 500
    assert (
        response.json()["detail"]
        == "API key auth is enabled but BACKEND_API_KEY is not configured."
    )
