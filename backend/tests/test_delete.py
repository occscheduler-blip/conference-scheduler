from types import SimpleNamespace
from uuid import uuid4

from app.supabase_io import delete


def test_delete_timeframes_returns_count_for_uuid(fake_supabase, monkeypatch):
    linked_id = uuid4()
    fake_supabase.table("timeframes").response = SimpleNamespace(data=[], count=3)
    monkeypatch.setattr(delete, "supabase", fake_supabase)

    deleted = delete.delete_timeframes(linked_id)

    assert deleted == 3
    actions = fake_supabase.queries["timeframes"].actions
    assert ("delete", None) in actions
    assert ("eq", {"field": "linked_id", "value": linked_id}) in actions


def test_delete_class_cascades_students_professors_presentations(monkeypatch):
    class_id = uuid4()
    student_id = uuid4()
    professor_id = uuid4()
    presentation_id = uuid4()
    calls = []

    monkeypatch.setattr(
        delete.read,
        "get_students",
        lambda class_id: SimpleNamespace(data=[{"id": str(student_id)}]),
    )
    monkeypatch.setattr(
        delete.read,
        "get_professors",
        lambda class_id: SimpleNamespace(data=[{"id": str(professor_id)}]),
    )
    monkeypatch.setattr(
        delete.read,
        "get_presentations",
        lambda class_id: SimpleNamespace(data=[{"id": str(presentation_id)}]),
    )
    monkeypatch.setattr(delete, "delete_student", lambda student_id: calls.append(("student", student_id)))
    monkeypatch.setattr(delete, "delete_professor", lambda prof_id: calls.append(("professor", prof_id)))
    monkeypatch.setattr(
        delete,
        "delete_presentation",
        lambda presentation_id: calls.append(("presentation", presentation_id)),
    )

    class FakeDeleteQuery:
        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class FakeClassTable:
        def delete(self):
            return FakeDeleteQuery()

    class FakeSupabase:
        def table(self, name):
            assert name == "classes"
            return FakeClassTable()

    monkeypatch.setattr(delete, "supabase", FakeSupabase())

    delete.delete_class(class_id)

    assert ("student", student_id) in calls
    assert ("professor", professor_id) in calls
    assert ("presentation", presentation_id) in calls


def test_delete_department_list_short_circuits_to_bulk_delete(monkeypatch):
    department_ids = [uuid4(), uuid4()]
    called = {"bulk": False, "get_classes": False}

    def fake_bulk(ids):
        called["bulk"] = ids == department_ids

    def fake_get_classes(_department_id):
        called["get_classes"] = True
        return SimpleNamespace(data=[])

    monkeypatch.setattr(delete, "delete_multiple_departments", fake_bulk)
    monkeypatch.setattr(delete.read, "get_classes", fake_get_classes)

    delete.delete_department(department_ids)

    assert called["bulk"] is True
    assert called["get_classes"] is False


def test_delete_symposium_deletes_child_departments(monkeypatch):
    symposium_id = uuid4()
    department_id = uuid4()
    calls = []

    monkeypatch.setattr(
        delete.read,
        "get_departments",
        lambda symposium_id: SimpleNamespace(data=[{"id": str(department_id)}]),
    )
    monkeypatch.setattr(
        delete,
        "delete_department",
        lambda dept_id: calls.append(("department", dept_id)),
    )
    monkeypatch.setattr(
        delete,
        "delete_timeframes",
        lambda linked_id: calls.append(("timeframes", linked_id)),
    )

    class FakeDeleteQuery:
        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class FakeSymposiumTable:
        def delete(self):
            return FakeDeleteQuery()

    class FakeSupabase:
        def table(self, name):
            assert name == "symposiums"
            return FakeSymposiumTable()

    monkeypatch.setattr(delete, "supabase", FakeSupabase())

    delete.delete_symposium(symposium_id)

    assert ("department", department_id) in calls
    assert ("timeframes", symposium_id) in calls
