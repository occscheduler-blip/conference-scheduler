"""Tests for supabase_io.nested_read — optional nested data fetching."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

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


# ---------------------------------------------------------------------------
# parse_include
# ---------------------------------------------------------------------------


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
        # "classes" is not in CLASS_ALLOWS (it's the starting level for that endpoint)
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


# ---------------------------------------------------------------------------
# Select string builders
# ---------------------------------------------------------------------------


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
        # Presentations and timeframes are handled separately — not in the select string
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
        # Presentations always go through the separate enrichment pass
        result = build_class_select(frozenset({"presentations"}))
        assert "presentations" not in result
        assert result == "*"


# ---------------------------------------------------------------------------
# _group_by helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# get_departments_nested (uses fake_supabase for nested select support)
# ---------------------------------------------------------------------------


class TestGetDepartmentsNested:
    def test_no_classes_include_returns_flat_departments(self, fake_supabase):
        dept_id = str(uuid4())
        sym_id = str(uuid4())
        fake_supabase.seed("departments", [
            {"id": dept_id, "department_name": "CS", "symposium_id": sym_id}
        ])

        result = get_departments_nested(None, frozenset())
        assert len(result) == 1
        assert result[0]["department_name"] == "CS"
        assert "classes" not in result[0]

    def test_with_classes_include(self, fake_supabase):
        dept_id = str(uuid4())
        class_id = str(uuid4())
        fake_supabase.seed("departments", [{"id": dept_id, "department_name": "CS"}])
        fake_supabase.seed("classes", [
            {"id": class_id, "name": "CS101", "department_id": dept_id}
        ])

        result = get_departments_nested(None, frozenset({"classes"}))
        assert len(result) == 1
        assert len(result[0]["classes"]) == 1
        assert result[0]["classes"][0]["name"] == "CS101"

    def test_with_classes_and_students(self, fake_supabase):
        dept_id = str(uuid4())
        class_id = str(uuid4())
        student_id = str(uuid4())
        fake_supabase.seed("departments", [{"id": dept_id, "department_name": "CS"}])
        fake_supabase.seed("classes", [
            {"id": class_id, "name": "CS101", "department_id": dept_id}
        ])
        fake_supabase.seed("students", [
            {"id": student_id, "name": "Alice", "class_id": class_id}
        ])

        result = get_departments_nested(None, frozenset({"classes", "students"}))
        cls = result[0]["classes"][0]
        assert len(cls["students"]) == 1
        assert cls["students"][0]["name"] == "Alice"

    def test_symposium_id_filter(self, fake_supabase):
        sym_a = str(uuid4())
        sym_b = str(uuid4())
        fake_supabase.seed("departments", [
            {"id": str(uuid4()), "department_name": "CS", "symposium_id": sym_a},
            {"id": str(uuid4()), "department_name": "Math", "symposium_id": sym_b},
        ])

        from uuid import UUID
        result = get_departments_nested(UUID(sym_a), frozenset({"classes"}))
        assert len(result) == 1
        assert result[0]["department_name"] == "CS"

    def test_empty_departments_returns_empty_list(self, fake_supabase):
        result = get_departments_nested(None, frozenset({"classes", "students"}))
        assert result == []


# ---------------------------------------------------------------------------
# get_classes_nested (uses fake_supabase)
# ---------------------------------------------------------------------------


class TestGetClassesNested:
    def test_no_includes_returns_flat_classes(self, fake_supabase):
        class_id = str(uuid4())
        fake_supabase.seed("classes", [{"id": class_id, "name": "CS101"}])

        result = get_classes_nested(None, frozenset())
        assert len(result) == 1
        assert "professors" not in result[0]

    def test_with_professors(self, fake_supabase):
        class_id = str(uuid4())
        prof_id = str(uuid4())
        fake_supabase.seed("classes", [{"id": class_id, "name": "CS101"}])
        fake_supabase.seed("professors", [
            {"id": prof_id, "name": "Dr. Smith", "class_id": class_id}
        ])

        result = get_classes_nested(None, frozenset({"professors"}))
        assert len(result[0]["professors"]) == 1
        assert result[0]["professors"][0]["name"] == "Dr. Smith"

    def test_professors_isolated_to_their_class(self, fake_supabase):
        class_a = str(uuid4())
        class_b = str(uuid4())
        fake_supabase.seed("classes", [
            {"id": class_a, "name": "CS101"},
            {"id": class_b, "name": "CS201"},
        ])
        fake_supabase.seed("professors", [
            {"id": str(uuid4()), "name": "Prof A", "class_id": class_a},
            {"id": str(uuid4()), "name": "Prof B", "class_id": class_b},
        ])

        result = get_classes_nested(None, frozenset({"professors"}))
        by_name = {c["name"]: c for c in result}
        assert len(by_name["CS101"]["professors"]) == 1
        assert len(by_name["CS201"]["professors"]) == 1
        assert by_name["CS101"]["professors"][0]["name"] == "Prof A"

    def test_empty_classes_returns_empty_list(self, fake_supabase):
        result = get_classes_nested(None, frozenset({"professors", "students"}))
        assert result == []


# ---------------------------------------------------------------------------
# Router integration via TestClient (status codes only)
# ---------------------------------------------------------------------------


class TestDepartmentsRouteInclude:
    def test_no_include_unchanged(self, client, api_headers):
        resp = client.get("/api/events/departments", headers=api_headers)
        assert resp.status_code == 200

    def test_invalid_include_returns_422(self, client, api_headers):
        resp = client.get(
            "/api/events/departments?include=symposia", headers=api_headers
        )
        assert resp.status_code == 422

    def test_valid_include_classes(self, client, api_headers):
        resp = client.get(
            "/api/events/departments?include=classes", headers=api_headers
        )
        assert resp.status_code == 200

    def test_classes_auto_promoted_when_requesting_students(self, client, api_headers):
        resp = client.get(
            "/api/events/departments?include=students", headers=api_headers
        )
        assert resp.status_code == 200


class TestClassesRouteInclude:
    def test_no_include_unchanged(self, client, api_headers):
        resp = client.get("/api/events/classes", headers=api_headers)
        assert resp.status_code == 200

    def test_invalid_include_returns_422(self, client, api_headers):
        resp = client.get("/api/events/classes?include=classes", headers=api_headers)
        assert resp.status_code == 422

    def test_valid_include_professors(self, client, api_headers):
        resp = client.get("/api/events/classes?include=professors", headers=api_headers)
        assert resp.status_code == 200

    def test_valid_include_all(self, client, api_headers):
        resp = client.get(
            "/api/events/classes?include=professors,students,presentations,timeframes",
            headers=api_headers,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Full integration tests with fake in-memory Supabase
# ---------------------------------------------------------------------------


class TestNestedFetchIntegration:
    def test_departments_with_classes_nested(self, integration_client, fake_supabase, api_headers):
        sym_id = str(uuid4())
        dept_id = str(uuid4())
        class_id = str(uuid4())
        fake_supabase.seed("departments", [
            {"id": dept_id, "department_name": "CS", "symposium_id": sym_id}
        ])
        fake_supabase.seed("classes", [
            {"id": class_id, "name": "CS101", "department_id": dept_id}
        ])

        resp = integration_client.get(
            f"/api/events/departments?symposium_id={sym_id}&include=classes",
            headers=api_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["department_name"] == "CS"
        assert len(data[0]["classes"]) == 1
        assert data[0]["classes"][0]["name"] == "CS101"

    def test_departments_no_include_backward_compat(self, integration_client, fake_supabase, api_headers):
        sym_id = str(uuid4())
        dept_id = str(uuid4())
        fake_supabase.seed("departments", [
            {"id": dept_id, "department_name": "CS", "symposium_id": sym_id}
        ])

        resp = integration_client.get(
            f"/api/events/departments?symposium_id={sym_id}",
            headers=api_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Original format: {"data": [...], "departments": [...]}
        assert "data" in data
        assert data["data"][0]["department_name"] == "CS"

    def test_classes_with_students_nested(self, integration_client, fake_supabase, api_headers):
        dept_id = str(uuid4())
        class_id = str(uuid4())
        student_id = str(uuid4())
        fake_supabase.seed("classes", [
            {"id": class_id, "name": "CS101", "department_id": dept_id}
        ])
        fake_supabase.seed("students", [
            {"id": student_id, "name": "Alice", "class_id": class_id}
        ])

        resp = integration_client.get(
            f"/api/events/classes?department_id={dept_id}&include=students",
            headers=api_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "CS101"
        assert len(data[0]["students"]) == 1
        assert data[0]["students"][0]["name"] == "Alice"

    def test_departments_auto_promotes_classes(self, integration_client, fake_supabase, api_headers):
        sym_id = str(uuid4())
        dept_id = str(uuid4())
        class_id = str(uuid4())
        student_id = str(uuid4())
        fake_supabase.seed("departments", [
            {"id": dept_id, "department_name": "CS", "symposium_id": sym_id}
        ])
        fake_supabase.seed("classes", [
            {"id": class_id, "name": "CS101", "department_id": dept_id}
        ])
        fake_supabase.seed("students", [
            {"id": student_id, "name": "Alice", "class_id": class_id}
        ])

        # Request "students" without explicitly requesting "classes" — should auto-promote
        resp = integration_client.get(
            f"/api/events/departments?symposium_id={sym_id}&include=students",
            headers=api_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "classes" in data[0]
        assert data[0]["classes"][0]["students"][0]["name"] == "Alice"

    def test_classes_with_professors_and_students(self, integration_client, fake_supabase, api_headers):
        dept_id = str(uuid4())
        class_id = str(uuid4())
        fake_supabase.seed("classes", [
            {"id": class_id, "name": "CS101", "department_id": dept_id}
        ])
        fake_supabase.seed("professors", [
            {"id": str(uuid4()), "name": "Dr. Smith", "class_id": class_id}
        ])
        fake_supabase.seed("students", [
            {"id": str(uuid4()), "name": "Alice", "class_id": class_id},
            {"id": str(uuid4()), "name": "Bob", "class_id": class_id},
        ])

        resp = integration_client.get(
            f"/api/events/classes?department_id={dept_id}&include=professors,students",
            headers=api_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        cls = data[0]
        assert cls["professors"][0]["name"] == "Dr. Smith"
        assert len(cls["students"]) == 2
