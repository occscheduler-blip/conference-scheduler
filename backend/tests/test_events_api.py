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

    def fake_insert(table_name, payload):
        write_calls.append((table_name, payload))
        return SimpleNamespace(data=payload)

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
    assert body["status"] == "inserted"
    assert body["symposium_id"] == symposium_id
    assert body["records_inserted"] == {"symposiums": 1, "timeframes": 1}
    assert [name for name, _payload in write_calls] == ["timeframes", "symposiums"]


def test_add_symposium_returns_500_on_unexpected_write_error(client, monkeypatch):
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
