"""Tests for supabase_io.nested_read — optional nested data fetching."""

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.supabase_io.nested_read import (
    CLASS_ALLOWS,
    CLASS_CHILDREN,
    DEPARTMENT_ALLOWS,
    VALID_INCLUDES,
    _group_by,
    build_class_select,
    build_department_select,
    get_classes_nested,
    get_departments_nested,
    parse_include,
)


# ── Shared helpers ─────────────────────────────────────────────────────────

TF_1 = {"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}


def _seed_chain(client: TestClient, h: dict[str, str], db) -> dict[str, str]:
    """Create symposium → department → class (+ professor) → students."""
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
            "professors": [{"name": "Prof. Smith", "email": "smith@hamilton.edu"}],
        },
        headers=h,
    )
    class_id = resp.json()["class_id"]

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

    return {
        "symposium_id": sym_id,
        "department_id": dept_id,
        "class_id": class_id,
    }


# ── parse_include (pure, no DB needed) ────────────────────────────────────


class TestParseInclude:
    def test_none_returns_empty(self):
        assert parse_include(None, DEPARTMENT_ALLOWS) == frozenset()

    def test_empty_string_returns_empty(self):
        assert parse_include("", DEPARTMENT_ALLOWS) == frozenset()

    def test_single_valid_token(self):
        assert parse_include("classes", DEPARTMENT_ALLOWS) == frozenset({"classes"})

    def test_multiple_valid_tokens(self):
        result = parse_include("classes,students,professors", DEPARTMENT_ALLOWS)
        assert result == frozenset({"classes", "students", "professors"})

    def test_strips_whitespace(self):
        result = parse_include("classes, students , professors", DEPARTMENT_ALLOWS)
        assert result == frozenset({"classes", "students", "professors"})

    def test_invalid_token_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_include("symposia", DEPARTMENT_ALLOWS)
        assert exc_info.value.status_code == 422
        assert "symposia" in exc_info.value.detail

    def test_disallowed_for_endpoint_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_include("classes", CLASS_ALLOWS)
        assert exc_info.value.status_code == 422

    def test_all_valid_includes_accepted_for_departments(self):
        raw = ",".join(VALID_INCLUDES)
        result = parse_include(raw, DEPARTMENT_ALLOWS)
        assert result == VALID_INCLUDES

    def test_mixed_valid_invalid_raises_422(self):
        with pytest.raises(HTTPException):
            parse_include("classes,nonsense", DEPARTMENT_ALLOWS)


# ── Select string builders (pure, no DB needed) ───────────────────────────


class TestBuildDepartmentSelect:
    def test_no_classes_returns_star(self):
        assert build_department_select(frozenset()) == "*"
        assert build_department_select(frozenset({"presentations"})) == "*"

    def test_classes_only(self):
        result = build_department_select(frozenset({"classes"}))
        assert result == "*, classes(*)"

    def test_classes_and_professors(self):
        result = build_department_select(frozenset({"classes", "professors"}))
        assert "classes(" in result
        assert "professors(*)" in result

    def test_classes_and_students(self):
        result = build_department_select(frozenset({"classes", "students"}))
        assert "students(*)" in result

    def test_all_children(self):
        result = build_department_select(
            frozenset({"classes", "professors", "students", "presentations", "timeframes"})
        )
        assert "presentations" not in result
        assert "timeframes" not in result
        assert "professors(*)" in result
        assert "students(*)" in result


class TestBuildClassSelect:
    def test_no_children_returns_star(self):
        assert build_class_select(frozenset()) == "*"

    def test_professors_only(self):
        result = build_class_select(frozenset({"professors"}))
        assert "professors(*)" in result

    def test_students_only(self):
        result = build_class_select(frozenset({"students"}))
        assert "students(*)" in result

    def test_presentations_not_in_select(self):
        result = build_class_select(frozenset({"presentations"}))
        assert "presentations" not in result
        assert result == "*"


# ── _group_by helper (pure) ───────────────────────────────────────────────


class TestGroupBy:
    def test_groups_correctly(self):
        rows = [
            {"class_id": "a", "name": "Alice"},
            {"class_id": "b", "name": "Bob"},
            {"class_id": "a", "name": "Carol"},
        ]
        result = _group_by(rows, "class_id")
        assert len(result["a"]) == 2
        assert len(result["b"]) == 1

    def test_missing_key_goes_to_empty_string_bucket(self):
        rows = [{"name": "Alice"}]
        result = _group_by(rows, "class_id")
        assert "" in result


# ── get_departments_nested (Docker Supabase) ──────────────────────────────


class TestGetDepartmentsNested:
    def test_no_includes_returns_flat(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_departments_nested(None, frozenset())
        assert len(result) == 1
        assert result[0]["department_name"] == "CS"
        assert "classes" not in result[0]

    def test_with_classes_include(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_departments_nested(
            UUID(ids["symposium_id"]), frozenset({"classes"})
        )
        assert len(result) == 1
        assert len(result[0]["classes"]) == 1
        assert result[0]["classes"][0]["name"] == "CS101"

    def test_with_classes_and_students(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_departments_nested(
            UUID(ids["symposium_id"]), frozenset({"classes", "students"})
        )
        cls = result[0]["classes"][0]
        assert len(cls["students"]) == 2

    def test_symposium_id_filter(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_departments_nested(UUID(ids["symposium_id"]), frozenset({"classes"}))
        assert len(result) == 1

        # Unrelated symposium should return nothing
        result = get_departments_nested(uuid4(), frozenset({"classes"}))
        assert result == []

    def test_empty_departments_returns_empty_list(self, client, h, db):
        result = get_departments_nested(None, frozenset({"classes", "students"}))
        assert result == []


# ── get_classes_nested (Docker Supabase) ──────────────────────────────────


class TestGetClassesNested:
    def test_no_includes_returns_flat(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_classes_nested(None, frozenset())
        assert len(result) == 1
        assert "professors" not in result[0]

    def test_with_professors(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_classes_nested(
            UUID(ids["department_id"]), frozenset({"professors"})
        )
        assert len(result) == 1
        assert len(result[0]["professors"]) == 1
        assert result[0]["professors"][0]["name"] == "Prof. Smith"

    def test_with_students(self, client, h, db):
        ids = _seed_chain(client, h, db)
        result = get_classes_nested(
            UUID(ids["department_id"]), frozenset({"students"})
        )
        assert len(result[0]["students"]) == 2

    def test_empty_classes_returns_empty_list(self, client, h, db):
        result = get_classes_nested(None, frozenset({"professors", "students"}))
        assert result == []


# ── Route-level include parameter (Docker Supabase) ───────────────────────


class TestDepartmentsRouteInclude:
    def test_no_include(self, client, h):
        resp = client.get("/api/events/departments", headers=h)
        assert resp.status_code == 200

    def test_invalid_include_returns_422(self, client, h):
        resp = client.get("/api/events/departments?include=symposia", headers=h)
        assert resp.status_code == 422

    def test_valid_include_classes(self, client, h, db):
        _seed_chain(client, h, db)
        resp = client.get("/api/events/departments?include=classes", headers=h)
        assert resp.status_code == 200

    def test_auto_promotes_classes_when_requesting_students(self, client, h, db):
        _seed_chain(client, h, db)
        resp = client.get("/api/events/departments?include=students", headers=h)
        assert resp.status_code == 200


class TestClassesRouteInclude:
    def test_no_include(self, client, h):
        resp = client.get("/api/events/classes", headers=h)
        assert resp.status_code == 200

    def test_invalid_include_returns_422(self, client, h):
        resp = client.get("/api/events/classes?include=classes", headers=h)
        assert resp.status_code == 422

    def test_valid_include_professors(self, client, h, db):
        _seed_chain(client, h, db)
        resp = client.get("/api/events/classes?include=professors", headers=h)
        assert resp.status_code == 200

    def test_valid_include_all(self, client, h, db):
        _seed_chain(client, h, db)
        resp = client.get(
            "/api/events/classes?include=professors,students,presentations,timeframes",
            headers=h,
        )
        assert resp.status_code == 200
