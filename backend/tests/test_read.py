from uuid import uuid4

import pytest

from app.supabase_io import read


@pytest.mark.parametrize(
    ("fn_name", "arg_name"),
    [
        ("get_classes", "department_id"),
        ("get_students", "class_id"),
        ("get_professors", "class_id"),
        ("get_presentations", "class_id"),
        ("get_presenting_students", "presentation_id"),
        ("get_timeframes", "linked_id"),
    ],
)
def test_read_helpers_apply_eq_for_single_uuid(
    fn_name, arg_name, fake_supabase, monkeypatch
):
    monkeypatch.setattr(read, "supabase", fake_supabase)
    fn = getattr(read, fn_name)

    value = uuid4()
    fn(**{arg_name: value})

    table_name = {
        "get_classes": "classes",
        "get_students": "students",
        "get_professors": "professors",
        "get_presentations": "presentations",
        "get_presenting_students": "presenting_students",
        "get_timeframes": "timeframes",
    }[fn_name]
    actions = fake_supabase.queries[table_name].actions
    assert ("eq", {"field": arg_name, "value": value}) in actions


def test_get_classes_uses_in_for_uuid_list(fake_supabase, monkeypatch):
    monkeypatch.setattr(read, "supabase", fake_supabase)
    ids = [uuid4(), uuid4()]

    read.get_classes(department_id=ids)

    actions = fake_supabase.queries["classes"].actions
    assert ("in_", {"field": "department_id", "values": ids}) in actions


def test_get_classes_rejects_invalid_type(fake_supabase, monkeypatch):
    monkeypatch.setattr(read, "supabase", fake_supabase)
    with pytest.raises(ValueError, match="department_id must be a UUID or list of UUIDs"):
        read.get_classes(department_id="not-a-uuid")


def test_get_presentations_enriches_with_presenting_student_records(
    fake_supabase, monkeypatch
):
    monkeypatch.setattr(read, "supabase", fake_supabase)
    presentation_id = uuid4()
    student_id = uuid4()
    fake_supabase.queries["presentations"] = fake_supabase.table("presentations")
    fake_supabase.queries["presentations"].response.data = [
        {"id": presentation_id, "title": "Capstone Talk"}
    ]
    fake_supabase.queries["presenting_students"] = fake_supabase.table(
        "presenting_students"
    )
    fake_supabase.queries["presenting_students"].response.data = [
        {"presentation_id": presentation_id, "student_id": student_id}
    ]
    fake_supabase.queries["students"] = fake_supabase.table("students")
    fake_supabase.queries["students"].response.data = [
        {"id": student_id, "name": "Ada Lovelace"}
    ]

    response = read.get_presentations()

    assert response.data == [
        {
            "id": presentation_id,
            "title": "Capstone Talk",
            "presenting_students": [{"id": student_id, "name": "Ada Lovelace"}],
        }
    ]


def test_get_prof_requests_applies_both_filters(fake_supabase, monkeypatch):
    monkeypatch.setattr(read, "supabase", fake_supabase)
    student_id = uuid4()
    professor_id = uuid4()

    read.get_prof_requests(student_id=student_id, professor_id=professor_id)

    actions = fake_supabase.queries["prof_requests"].actions
    assert ("eq", {"field": "student_id", "value": student_id}) in actions
    assert ("eq", {"field": "professor_id", "value": professor_id}) in actions
