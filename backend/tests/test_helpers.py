"""Tests for helper functions in app.routers.events."""

from types import SimpleNamespace
from uuid import uuid4, UUID

from app.routers.events import (
    _normalize_counts,
    _rows_affected,
    _serialize_update_fields,
    _sum_counts,
)


# ---------------------------------------------------------------------------
# _serialize_update_fields
# ---------------------------------------------------------------------------
class TestSerializeUpdateFields:
    def test_uuid_converted_to_str(self):
        uid = uuid4()
        result = _serialize_update_fields({"class_id": uid, "name": "Bio"})
        assert result["class_id"] == str(uid)
        assert result["name"] == "Bio"

    def test_empty_dict(self):
        assert _serialize_update_fields({}) == {}

    def test_non_uuid_values_unchanged(self):
        result = _serialize_update_fields({"a": 1, "b": "hello", "c": None})
        assert result == {"a": 1, "b": "hello", "c": None}


# ---------------------------------------------------------------------------
# _rows_affected
# ---------------------------------------------------------------------------
class TestRowsAffected:
    def test_dict_with_count(self):
        assert _rows_affected({"count": 5}) == 5

    def test_dict_with_data_list(self):
        assert _rows_affected({"data": [1, 2, 3]}) == 3

    def test_dict_with_data_dict(self):
        assert _rows_affected({"data": {"id": "x"}}) == 1

    def test_dict_fallback(self):
        assert _rows_affected({}, fallback=7) == 7

    def test_object_with_count(self):
        resp = SimpleNamespace(count=10)
        assert _rows_affected(resp) == 10

    def test_object_with_data_list(self):
        resp = SimpleNamespace(data=[1, 2])
        assert _rows_affected(resp) == 2

    def test_object_with_data_dict(self):
        resp = SimpleNamespace(data={"x": 1})
        assert _rows_affected(resp) == 1

    def test_object_fallback(self):
        resp = SimpleNamespace()
        assert _rows_affected(resp, fallback=3) == 3

    def test_negative_count_ignored(self):
        assert _rows_affected({"count": -1}, fallback=0) == 0

    def test_none_data_uses_fallback(self):
        assert _rows_affected({"data": None}, fallback=4) == 4


# ---------------------------------------------------------------------------
# _normalize_counts
# ---------------------------------------------------------------------------
class TestNormalizeCounts:
    def test_valid_dict(self):
        result = _normalize_counts({"a": 1, "b": 2}, {"x": 0})
        assert result == {"a": 1, "b": 2}

    def test_filters_negative(self):
        result = _normalize_counts({"a": -1, "b": 3}, {"x": 0})
        assert result == {"b": 3}

    def test_none_returns_fallback(self):
        assert _normalize_counts(None, {"f": 9}) == {"f": 9}

    def test_empty_dict_returns_fallback(self):
        assert _normalize_counts({}, {"f": 1}) == {"f": 1}

    def test_all_invalid_returns_fallback(self):
        assert _normalize_counts({"a": -5}, {"f": 2}) == {"f": 2}

    def test_non_dict_returns_fallback(self):
        assert _normalize_counts("bad", {"f": 0}) == {"f": 0}


# ---------------------------------------------------------------------------
# _sum_counts
# ---------------------------------------------------------------------------
class TestSumCounts:
    def test_single_group(self):
        assert _sum_counts({"a": 1, "b": 2}) == 3

    def test_multiple_groups(self):
        assert _sum_counts({"a": 1}, {"b": 2}, {"c": 3}) == 6

    def test_empty(self):
        assert _sum_counts() == 0

    def test_ignores_negative(self):
        assert _sum_counts({"a": -1, "b": 5}) == 5

    def test_ignores_non_int(self):
        assert _sum_counts({"a": "bad", "b": 2}) == 2
