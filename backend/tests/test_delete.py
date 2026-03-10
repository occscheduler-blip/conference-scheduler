"""Tests for supabase_io.delete cascade logic."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.supabase_io import delete


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
        target = {}
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
        target = {}
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


class TestDeleteTimeframes:
    def test_calls_delete_with_uuid(self, mock_supabase):
        uid = uuid4()

        def _table(name):
            table = MagicMock()
            for m in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
                getattr(table, m).return_value = table
            # The count query returns count=2
            table.execute.return_value = SimpleNamespace(data=[], count=2)
            return table

        mock_supabase.table.side_effect = _table
        result = delete.delete_timeframes(uid)
        assert result == 2


class TestDeleteStudent:
    def test_returns_count_dict(self, mock_supabase):
        uid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        result = delete.delete_student(uid)
        assert "students" in result
        assert "presenting_students" in result
        assert "prof_requests" in result
        assert "timeframes" in result
        for key, val in result.items():
            assert isinstance(val, int), f"{key} is not int: {val!r}"
            assert val >= 0, f"{key} is negative: {val}"


class TestDeleteProfessor:
    def test_returns_count_dict(self, mock_supabase):
        uid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        result = delete.delete_professor(uid)
        assert "professors" in result
        assert "prof_requests" in result
        assert "timeframes" in result
        for key, val in result.items():
            assert isinstance(val, int), f"{key} is not int: {val!r}"
            assert val >= 0, f"{key} is negative: {val}"


class TestDeletePresentation:
    def test_returns_count_dict(self, mock_supabase):
        uid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=1
        )
        result = delete.delete_presentation(uid)
        assert "presentations" in result
        assert "presenting_students" in result
        assert "timeframes" in result
        for key, val in result.items():
            assert isinstance(val, int), f"{key} is not int: {val!r}"
            assert val >= 0, f"{key} is negative: {val}"


class TestDeleteClass:
    def test_cascade_empty_class(self, mock_supabase):
        """Deleting a class with no students/professors/presentations."""
        uid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        result = delete.delete_class(uid)
        assert "classes" in result

    def test_list_dispatches_to_multiple(self, mock_supabase):
        uids = [uuid4(), uuid4()]
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        result = delete.delete_class(uids)
        assert isinstance(result, dict)


class TestDeleteDepartment:
    def test_cascade_empty_department(self, mock_supabase):
        uid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        result = delete.delete_department(uid)
        assert "departments" in result

    def test_list_dispatches(self, mock_supabase):
        uids = [uuid4(), uuid4()]
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        result = delete.delete_department(uids)
        assert isinstance(result, dict)


class TestDeleteSymposium:
    def test_cascade_empty_symposium(self, mock_supabase):
        uid = uuid4()
        mock_supabase.table.return_value.execute.return_value = SimpleNamespace(
            data=[], count=0
        )
        result = delete.delete_symposium(uid)
        assert "symposia" in result
        assert "timeframes" in result
