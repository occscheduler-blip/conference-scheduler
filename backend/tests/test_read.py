"""Tests for supabase_io.read query builder functions."""

from types import SimpleNamespace
from uuid import uuid4, UUID

import pytest

from app.supabase_io import read


class TestGetSymposia:
    def test_calls_symposia_table(self, mock_supabase):
        read.get_symposia()
        mock_supabase.table.assert_called_with("symposia")


class TestGetDepartments:
    def test_no_filter(self, mock_supabase):
        read.get_departments()
        mock_supabase.table.assert_called_with("departments")

    def test_with_symposium_filter(self, mock_supabase):
        uid = uuid4()
        read.get_departments(symposium_id=uid)
        # Verify table was called for departments
        mock_supabase.table.assert_called_with("departments")


class TestGetClasses:
    def test_no_filter(self, mock_supabase):
        read.get_classes()
        mock_supabase.table.assert_called_with("classes")

    def test_single_uuid_filter(self, mock_supabase):
        uid = uuid4()
        read.get_classes(department_id=uid)
        mock_supabase.table.assert_called_with("classes")

    def test_list_uuid_filter(self, mock_supabase):
        uids = [uuid4(), uuid4()]
        read.get_classes(department_id=uids)
        mock_supabase.table.assert_called_with("classes")

    def test_invalid_type_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="UUID"):
            read.get_classes(department_id="bad")


class TestGetStudents:
    def test_no_filter(self, mock_supabase):
        read.get_students()
        mock_supabase.table.assert_called_with("students")

    def test_invalid_type_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="UUID"):
            read.get_students(class_id="bad")


class TestGetProfessors:
    def test_no_filter(self, mock_supabase):
        read.get_professors()
        mock_supabase.table.assert_called_with("professors")

    def test_invalid_type_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="UUID"):
            read.get_professors(class_id=123)


class TestGetTimeframes:
    def test_no_filter(self, mock_supabase):
        read.get_timeframes()
        mock_supabase.table.assert_called_with("timeframes")

    def test_single_uuid(self, mock_supabase):
        uid = uuid4()
        read.get_timeframes(linked_id=uid)
        mock_supabase.table.assert_called_with("timeframes")

    def test_invalid_type_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="UUID"):
            read.get_timeframes(linked_id=999)


class TestGetPresentingStudents:
    def test_no_filter(self, mock_supabase):
        read.get_presenting_students()
        mock_supabase.table.assert_called_with("presenting_students")


class TestGetRequests:
    def test_no_filter(self, mock_supabase):
        read.get_requests()
        mock_supabase.table.assert_called_with("requests")

    def test_invalid_type_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="UUID"):
            read.get_requests(student_id="not-a-uuid")


class TestGetPresentationsEnrichment:
    """Test the presentation enrichment logic that joins presenting_students."""

    def test_enriches_presentations_with_students(self, mock_supabase):
        pres_id = str(uuid4())
        student_id = str(uuid4())

        def _table_side_effect(name):
            from unittest.mock import MagicMock
            table = MagicMock()
            for m in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
                getattr(table, m).return_value = table

            if name == "presentations":
                table.execute.return_value = SimpleNamespace(
                    data=[{"id": pres_id, "title": "Talk", "class_id": str(uuid4()), "minutes": 15}]
                )
            elif name == "presenting_students":
                table.execute.return_value = SimpleNamespace(
                    data=[{"presentation_id": pres_id, "student_id": student_id}]
                )
            elif name == "students":
                table.execute.return_value = SimpleNamespace(
                    data=[{"id": student_id, "name": "Alice", "email": "a@hamilton.edu"}]
                )
            else:
                table.execute.return_value = SimpleNamespace(data=[])
            return table

        mock_supabase.table.side_effect = _table_side_effect

        result = read.get_presentations()
        assert len(result.data) == 1
        assert result.data[0]["presenting_students"][0]["name"] == "Alice"

    def test_empty_presentations(self, mock_supabase):
        result = read.get_presentations()
        assert result.data == []
