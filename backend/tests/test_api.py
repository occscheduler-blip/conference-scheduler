"""Integration tests — all requests hit the real local Supabase Docker instance."""

from tests.builders import (
    TF_1,
    TF_2,
    add_class as _add_class,
    add_department as _add_department,
    add_presentation as _add_presentation,
    add_students as _add_students,
    add_symposium as _add_symposium,
)


# ── TestHealth ───────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── TestAuth ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_get_no_token_returns_401(self, client):
        """GET endpoints require a JWT."""
        resp = client.get("/api/events/symposiums")
        assert resp.status_code == 401

    def test_attendee_get_token_ok(self, client):
        from app.auth.jwt_utils import encode_jwt
        token = encode_jwt("00000000-0000-0000-0000-000000000099", "viewer@attendee.local", "attendee")
        resp = client.get("/api/events/symposiums", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_no_token_returns_401_on_protected(self, client):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "default_buffer": 0, "timeframes": []},
        )
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "default_buffer": 0, "timeframes": []},
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401

    def test_wrong_role_returns_403(self, client):
        from app.auth.jwt_utils import encode_jwt
        student_token = encode_jwt("00000000-0000-0000-0000-000000000099", "s@hamilton.edu", "student")
        resp = client.post(
            "/api/events/add_symposium",
            json={
                "symposium_name": "S", "rooms_available": 1, "default_buffer": 0,
                "timeframes": [{"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}],
            },
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 403

    def test_valid_token_accepted(self, client, h):
        resp = client.post(
            "/api/events/add_symposium",
            json={
                "symposium_name": "S", "rooms_available": 1, "default_buffer": 0,
                "timeframes": [{"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}],
            },
            headers=h,
        )
        assert resp.status_code == 200


# ── TestSymposiums ────────────────────────────────────────────────────────────

class TestSymposiums:
    def test_create_symposium(self, client, h, db):
        body = _add_symposium(client, h)
        assert body["status"] == "created"
        assert "symposium_id" in body
        assert db.count("symposiums") == 1
        assert db.count("timeframes") == 2

    def test_get_all_symposiums(self, client, h, db):
        _add_symposium(client, h, name="S1")
        _add_symposium(client, h, name="S2")
        resp = client.get("/api/events/symposiums", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

    def test_get_symposium_by_id(self, client, h, db):
        body = _add_symposium(client, h)
        sym_id = body["symposium_id"]
        resp = client.get(f"/api/events/symposiums/{sym_id}", headers=h)
        assert resp.status_code == 200
        result = resp.json()
        assert "symposium" in result
        assert "timeframes" in result
        assert result["symposium"]["id"] == sym_id
        assert len(result["timeframes"]) == 2

    def test_get_symposium_not_found(self, client, h):
        resp = client.get(
            "/api/events/symposiums/00000000-0000-0000-0000-000000000000", headers=h
        )
        assert resp.status_code == 404

    def test_update_symposium_updates_existing(self, client, h, db):
        body = _add_symposium(client, h)
        sym_id = body["symposium_id"]
        resp = client.put(
            "/api/events/update_symposium",
            json={
                "symposium_id": sym_id,
                "symposium_name": "Updated Name",
                "rooms_available": 10,
                "default_buffer": 0,
                "timeframes": [TF_1],
            },
            headers=h,
        )
        assert resp.status_code == 200
        assert db.count("symposiums") == 1  # still 1, not 2
        assert db.count("timeframes") == 1  # replaced 2 → 1
        row = db.rows("symposiums")[0]
        assert row["name"] == "Updated Name"
        assert row["rooms_available"] == 10

    def test_update_symposium(self, client, h, db):
        body = _add_symposium(client, h)
        sym_id = body["symposium_id"]
        resp = client.put(
            "/api/events/update_symposium",
            json={"symposium_id": sym_id, "symposium_name": "Renamed", "rooms_available": 7, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
        row = db.rows("symposiums")[0]
        assert row["name"] == "Renamed"
        assert row["rooms_available"] == 7

    def test_delete_symposium(self, client, h, db):
        body = _add_symposium(client, h)
        sym_id = body["symposium_id"]
        resp = client.delete(f"/api/events/delete_symposium?symposium_id={sym_id}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert db.count("symposiums") == 0
        assert db.count("timeframes") == 0

    def test_update_timeframes_replaces(self, client, h, db):
        body = _add_symposium(client, h)
        sym_id = body["symposium_id"]
        assert db.count("timeframes") == 2
        resp = client.put(
            "/api/events/update_timeframes",
            json={"linked_id": sym_id, "timeframes": [TF_1]},
            headers=h,
        )
        assert resp.status_code == 200
        assert db.count("timeframes") == 1


class TestBasicSchedule:
    def test_basic_schedule_respects_professor_unavailable_window(self, client, h):
        resp = client.post(
            "/api/events/basic_schedule",
            json={
                "day_start": "2026-04-20T09:00:00Z",
                "day_end": "2026-04-20T18:00:00Z",
                "presentation_minutes": 60,
                "room_count": 1,
                "professor_name": "Prof. Smith",
                "professor_unavailable": [
                    {
                        "start_time": "2026-04-20T14:00:00Z",
                        "end_time": "2026-04-20T17:00:00Z",
                    }
                ],
                "students": [
                    {"name": "Student 1"},
                    {"name": "Student 2"},
                    {"name": "Student 3"},
                    {"name": "Student 4"},
                    {"name": "Student 5"},
                    {"name": "Student 6"},
                ],
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in {"optimal", "feasible"}
        assert body["summary"]["scheduled_count"] == 6
        starts = [item["start_time"] for item in body["scheduled"]]
        assert starts == [
            "2026-04-20T09:00:00+00:00",
            "2026-04-20T10:00:00+00:00",
            "2026-04-20T11:00:00+00:00",
            "2026-04-20T12:00:00+00:00",
            "2026-04-20T13:00:00+00:00",
            "2026-04-20T17:00:00+00:00",
        ]
        assert all(item["room_index"] == 0 for item in body["scheduled"])


# ── TestDepartments ───────────────────────────────────────────────────────────

class TestDepartments:
    def _setup(self, client, h) -> str:
        return _add_symposium(client, h)["symposium_id"]

    def test_create_department(self, client, h, db):
        sym_id = self._setup(client, h)
        body = _add_department(client, h, sym_id)
        assert body["status"] == "Inserted"
        assert "department_id" in body
        assert db.count("departments") == 1

    def test_get_departments(self, client, h):
        sym_id = self._setup(client, h)
        _add_department(client, h, sym_id, name="CS")
        _add_department(client, h, sym_id, name="Biology")
        resp = client.get(
            f"/api/events/departments?symposium_id={sym_id}", headers=h
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_update_department(self, client, h, db):
        sym_id = self._setup(client, h)
        dept_id = _add_department(client, h, sym_id)["department_id"]
        resp = client.put(
            "/api/events/update_department",
            json={
                "department_id": dept_id,
                "department_name": "New Name",
                "department_head_name": "Dr. New",
                "email": "new@hamilton.edu",
            },
            headers=h,
        )
        assert resp.status_code == 200
        row = db.rows("departments")[0]
        assert row["department_name"] == "New Name"

    def test_delete_department(self, client, h, db):
        sym_id = self._setup(client, h)
        dept_id = _add_department(client, h, sym_id)["department_id"]
        resp = client.delete(
            f"/api/events/delete_department?department_id={dept_id}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("departments") == 0


# ── TestClasses ───────────────────────────────────────────────────────────────

class TestClasses:
    def _setup(self, client, h) -> dict[str, str]:
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        return {"symposium_id": sym_id, "department_id": dept_id}

    def test_create_class(self, client, h, db):
        ids = self._setup(client, h)
        body = _add_class(client, h, ids["department_id"])
        assert body["status"] == "Inserted"
        assert "class_id" in body
        assert db.count("classes") == 1
        assert db.count("professors") == 1

    def test_get_classes(self, client, h, db):
        ids = self._setup(client, h)
        _add_class(client, h, ids["department_id"], name="CS101")
        _add_class(client, h, ids["department_id"], name="CS102")
        resp = client.get(
            f"/api/events/classes?department_id={ids['department_id']}", headers=h
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_update_class(self, client, h, db):
        ids = self._setup(client, h)
        class_id = _add_class(client, h, ids["department_id"])["class_id"]
        resp = client.put(
            "/api/events/update_class",
            json={
                "class_id": class_id,
                "name": "CS999",
                "department_id": ids["department_id"],
            },
            headers=h,
        )
        assert resp.status_code == 200
        row = db.rows("classes")[0]
        assert row["name"] == "CS999"

    def test_delete_class(self, client, h, db):
        ids = self._setup(client, h)
        class_id = _add_class(client, h, ids["department_id"])["class_id"]
        resp = client.delete(
            f"/api/events/delete_class?class_id={class_id}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("classes") == 0


# ── TestStudents ──────────────────────────────────────────────────────────────

class TestStudents:
    def _setup(self, client, h) -> dict[str, str]:
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        class_id = _add_class(client, h, dept_id)["class_id"]
        return {"department_id": dept_id, "class_id": class_id}

    def test_add_students(self, client, h, db):
        ids = self._setup(client, h)
        body = _add_students(client, h, ids["class_id"], count=3)
        assert body["status"] == "inserted"
        assert db.count("students") == 3

    def test_get_students(self, client, h):
        ids = self._setup(client, h)
        _add_students(client, h, ids["class_id"], count=2)
        resp = client.get(
            f"/api/events/students?class_id={ids['class_id']}", headers=h
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_update_student(self, client, h, db):
        ids = self._setup(client, h)
        _add_students(client, h, ids["class_id"], count=1)
        student_id = str(db.rows("students")[0]["id"])

        # update_student requires a presentation_id — create one first
        pres_id = _add_presentation(client, h, ids["class_id"], [student_id])["presentation_id"]

        resp = client.put(
            "/api/events/update_student",
            json={
                "student_id": student_id,
                "name": "Updated Student",
                "email": "updated@hamilton.edu",
                "class_id": ids["class_id"],
                "presentation_id": pres_id,
            },
            headers=h,
        )
        assert resp.status_code == 200
        row = db.rows("students")[0]
        assert row["name"] == "Updated Student"

    def test_delete_student(self, client, h, db):
        ids = self._setup(client, h)
        _add_students(client, h, ids["class_id"], count=1)
        student_id = str(db.rows("students")[0]["id"])
        resp = client.delete(
            f"/api/events/delete_student?student_id={student_id}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("students") == 0


# ── TestProfessors ────────────────────────────────────────────────────────────

class TestProfessors:
    def _setup(self, client, h) -> dict[str, str]:
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        class_body = _add_class(client, h, dept_id)
        return {"class_id": class_body["class_id"], "professor_ids": class_body["professor_ids"]}

    def test_get_professors(self, client, h, db):
        ids = self._setup(client, h)
        resp = client.get(
            f"/api/events/professors?class_id={ids['class_id']}", headers=h
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_update_professor(self, client, h, db):
        ids = self._setup(client, h)
        prof_id = ids["professor_ids"][0]
        resp = client.put(
            "/api/events/update_professor",
            json={
                "professor_id": prof_id,
                "name": "Prof. Updated",
                "email": "updated@hamilton.edu",
                "class_id": ids["class_id"],
            },
            headers=h,
        )
        assert resp.status_code == 200
        row = db.rows("professors")[0]
        assert row["name"] == "Prof. Updated"

    def test_delete_professor(self, client, h, db):
        ids = self._setup(client, h)
        prof_id = ids["professor_ids"][0]
        resp = client.delete(
            f"/api/events/delete_professor?professor_id={prof_id}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("professors") == 0


# ── TestPresentations ─────────────────────────────────────────────────────────

class TestPresentations:
    def _setup(self, client, h, db) -> dict[str, str]:
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        class_id = _add_class(client, h, dept_id)["class_id"]
        _add_students(client, h, class_id, count=2)
        student_ids = [str(r["id"]) for r in db.rows("students")]
        return {"class_id": class_id, "student_ids": student_ids}

    def test_add_presentation(self, client, h, db):
        ids = self._setup(client, h, db)
        body = _add_presentation(client, h, ids["class_id"], ids["student_ids"])
        assert body["status"] == "inserted"
        assert db.count("presentations") == 1
        assert db.count("presenting_students") == 2

    def test_get_presentations_enriched(self, client, h, db):
        ids = self._setup(client, h, db)
        _add_presentation(client, h, ids["class_id"], ids["student_ids"])
        resp = client.get(
            f"/api/events/presentations?class_id={ids['class_id']}", headers=h
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert "presenting_students" in data[0]
        assert len(data[0]["presenting_students"]) == 2

    def test_update_presentation(self, client, h, db):
        ids = self._setup(client, h, db)
        pres_id = _add_presentation(client, h, ids["class_id"], ids["student_ids"])["presentation_id"]
        # Update with only one of the two students
        resp = client.put(
            "/api/events/update_presentation",
            json={
                "presentation_id": pres_id,
                "title": "Updated Title",
                "class_id": ids["class_id"],
                "minutes": 30,
                "buffer": 0,
                "presenting_students": [ids["student_ids"][0]],
            },
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
        row = db.rows("presentations")[0]
        assert row["title"] == "Updated Title"
        assert row["minutes"] == 30
        assert db.count("presenting_students") == 1

    def test_update_presentation_without_buffer_preserves_existing(self, client, h, db):
        ids = self._setup(client, h, db)
        pres_id = _add_presentation(client, h, ids["class_id"], ids["student_ids"], buffer=7)["presentation_id"]
        resp = client.put(
            "/api/events/update_presentation",
            json={
                "presentation_id": pres_id,
                "title": "Updated Title",
                "class_id": ids["class_id"],
                "minutes": 30,
                "presenting_students": [ids["student_ids"][0]],
            },
            headers=h,
        )
        assert resp.status_code == 200
        row = db.rows("presentations")[0]
        assert row["title"] == "Updated Title"
        assert row["minutes"] == 30
        assert row["buffer"] == 7

    def test_delete_presentation(self, client, h, db):
        ids = self._setup(client, h, db)
        pres_id = _add_presentation(client, h, ids["class_id"], ids["student_ids"])["presentation_id"]
        resp = client.delete(
            f"/api/events/delete_presentation?presentation_id={pres_id}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("presentations") == 0
        assert db.count("presenting_students") == 0


# ── TestRequests ──────────────────────────────────────────────────────────────

class TestRequests:
    def _setup(self, client, h, db) -> str:
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        class_id = _add_class(client, h, dept_id)["class_id"]
        _add_students(client, h, class_id, count=1)
        return str(db.rows("students")[0]["id"])

    def test_add_request(self, client, h, db):
        student_id = self._setup(client, h, db)
        resp = client.post(
            "/api/events/add_request",
            json={"name": "Prof. Pref", "email": "pref@hamilton.edu", "student_id": student_id},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "inserted"
        assert db.count("requests") == 1

    def test_get_requests(self, client, h, db):
        from app.auth.jwt_utils import encode_jwt

        student_id = self._setup(client, h, db)
        client.post(
            "/api/events/add_request",
            json={"name": "Prof. A", "email": "a@hamilton.edu", "student_id": student_id},
            headers=h,
        )
        student_headers = {
            "Authorization": f"Bearer {encode_jwt(student_id, 'student@hamilton.edu', 'student')}"
        }
        resp = client.get(
            f"/api/events/requests?student_id={student_id}", headers=student_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1


# ── TestCascadeDelete ─────────────────────────────────────────────────────────

class TestCascadeDelete:
    def _full_setup(self, client, h, db) -> dict[str, str]:
        """Build: symposium → department → class → students + professor → presentation + request."""
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        class_body = _add_class(client, h, dept_id)
        class_id = class_body["class_id"]
        _add_students(client, h, class_id, count=2)
        student_ids = [str(r["id"]) for r in db.rows("students")]
        _add_presentation(client, h, class_id, student_ids)
        # add a request for the first student
        client.post(
            "/api/events/add_request",
            json={"name": "Pref Prof", "email": "p@hamilton.edu", "student_id": student_ids[0]},
            headers=h,
        )
        return {
            "symposium_id": sym_id,
            "department_id": dept_id,
            "class_id": class_id,
        }

    def test_delete_class_cascades(self, client, h, db):
        ids = self._full_setup(client, h, db)
        resp = client.delete(
            f"/api/events/delete_class?class_id={ids['class_id']}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("classes") == 0
        assert db.count("professors") == 0
        assert db.count("students") == 0
        assert db.count("presentations") == 0
        assert db.count("presenting_students") == 0

    def test_delete_department_cascades(self, client, h, db):
        ids = self._full_setup(client, h, db)
        resp = client.delete(
            f"/api/events/delete_department?department_id={ids['department_id']}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("departments") == 0
        assert db.count("classes") == 0
        assert db.count("professors") == 0

    def test_delete_symposium_cascades_everything(self, client, h, db):
        ids = self._full_setup(client, h, db)
        resp = client.delete(
            f"/api/events/delete_symposium?symposium_id={ids['symposium_id']}", headers=h
        )
        assert resp.status_code == 200
        assert db.count("symposiums") == 0
        assert db.count("departments") == 0
        assert db.count("classes") == 0
        assert db.count("professors") == 0
        assert db.count("students") == 0
        assert db.count("presentations") == 0
        assert db.count("presenting_students") == 0
        assert db.count("timeframes") == 0
        assert db.count("requests") == 0


# ── TestNestedRead ────────────────────────────────────────────────────────────

class TestNestedRead:
    def _setup(self, client, h, db) -> dict[str, str]:
        sym_id = _add_symposium(client, h)["symposium_id"]
        dept_id = _add_department(client, h, sym_id)["department_id"]
        class_id = _add_class(client, h, dept_id)["class_id"]
        _add_students(client, h, class_id, count=2)
        return {"symposium_id": sym_id, "department_id": dept_id, "class_id": class_id}

    def test_departments_include_classes(self, client, h, db):
        ids = self._setup(client, h, db)
        resp = client.get(
            f"/api/events/departments?symposium_id={ids['symposium_id']}&include=classes",
            headers=h,
        )
        assert resp.status_code == 200
        depts = resp.json()
        assert isinstance(depts, list)
        assert len(depts) == 1
        assert "classes" in depts[0]
        assert len(depts[0]["classes"]) == 1

    def test_classes_include_students(self, client, h, db):
        ids = self._setup(client, h, db)
        resp = client.get(
            f"/api/events/classes?department_id={ids['department_id']}&include=students",
            headers=h,
        )
        assert resp.status_code == 200
        classes = resp.json()
        assert isinstance(classes, list)
        assert len(classes[0]["students"]) == 2

    def test_departments_include_students_auto_promotes_classes(self, client, h, db):
        ids = self._setup(client, h, db)
        resp = client.get(
            f"/api/events/departments?symposium_id={ids['symposium_id']}&include=students",
            headers=h,
        )
        assert resp.status_code == 200
        depts = resp.json()
        # classes promoted automatically; students nested inside each class
        assert "classes" in depts[0]
        for cls in depts[0]["classes"]:
            assert "students" in cls

    def test_classes_include_professors_and_students(self, client, h, db):
        ids = self._setup(client, h, db)
        resp = client.get(
            f"/api/events/classes?department_id={ids['department_id']}&include=professors,students",
            headers=h,
        )
        assert resp.status_code == 200
        classes = resp.json()
        assert "professors" in classes[0]
        assert "students" in classes[0]
        assert len(classes[0]["professors"]) == 1
        assert len(classes[0]["students"]) == 2
