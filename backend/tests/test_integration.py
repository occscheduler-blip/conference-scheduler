"""Full-stack integration tests against Docker Supabase.

These complement test_api.py by verifying:
  - Row count accuracy after operations
  - Upsert deduplication
  - Presentation enrichment with student details
  - Student update persistence
  - Timeframe replacement counts
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.builders import TF_1, TF_2


# ── Symposium lifecycle ───────────────────────────────────────────────────


class TestSymposiumCounts:
    def test_post_inserts_correct_timeframe_count(self, client, h, db):
        client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "Multi", "rooms_available": 4, "default_buffer": 0, "timeframes": [TF_1, TF_2]},
            headers=h,
        )
        assert db.count("symposiums") == 1
        assert db.count("timeframes") == 2

    def test_update_does_not_duplicate(self, client, h, db):
        """PUTting update_symposium updates — no duplicate."""
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "Original", "rooms_available": 2, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        sym_id = resp.json()["symposium_id"]
        assert db.count("symposiums") == 1

        client.put(
            "/api/events/update_symposium",
            json={
                "symposium_id": sym_id,
                "symposium_name": "Updated",
                "rooms_available": 10,
                "default_buffer": 0,
                "timeframes": [TF_2],
            },
            headers=h,
        )
        assert db.count("symposiums") == 1  # still 1
        row = db.rows("symposiums")[0]
        assert row["name"] == "Updated"
        assert row["rooms_available"] == 10


# ── Timeframe replacement ─────────────────────────────────────────────────


class TestTimeframeReplacement:
    def test_put_replaces_all_timeframes(self, client, h, db):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "default_buffer": 0, "timeframes": [TF_1, TF_2]},
            headers=h,
        )
        sym_id = resp.json()["symposium_id"]
        assert db.count("timeframes") == 2

        new_tf = {"start_time": "2026-05-01T09:00:00Z", "end_time": "2026-05-01T11:00:00Z"}
        resp = client.put(
            "/api/events/update_timeframes",
            json={"linked_id": sym_id, "timeframes": [new_tf]},
            headers=h,
        )
        assert resp.status_code == 200
        assert db.count("timeframes") == 1  # 2 old deleted, 1 new inserted


# ── Cascade delete counts ─────────────────────────────────────────────────


class TestCascadeDeleteCounts:
    def _seed(self, client, h, db):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        sym_id = resp.json()["symposium_id"]

        resp = client.post(
            "/api/events/add_department",
            json={
                "symposium_id": sym_id,
                "department_name": "CS",
                "department_head_name": "Dr. H",
                "email": "h@hamilton.edu",
            },
            headers=h,
        )
        dept_id = resp.json()["department_id"]

        resp = client.post(
            "/api/events/add_class",
            json={
                "name": "CS101",
                "department_id": dept_id,
                "professors": [{"name": "Prof", "email": "prof@hamilton.edu"}],
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

        return {"class_id": class_id}

    def test_delete_class_removes_professors(self, client, h, db):
        ids = self._seed(client, h, db)
        assert db.count("professors") == 1
        client.delete(f"/api/events/delete_class?class_id={ids['class_id']}", headers=h)
        assert db.count("professors") == 0

    def test_delete_class_removes_students(self, client, h, db):
        ids = self._seed(client, h, db)
        assert db.count("students") == 2
        client.delete(f"/api/events/delete_class?class_id={ids['class_id']}", headers=h)
        assert db.count("students") == 0

    def test_delete_class_response_counts(self, client, h, db):
        ids = self._seed(client, h, db)
        resp = client.delete(
            f"/api/events/delete_class?class_id={ids['class_id']}", headers=h
        )
        body = resp.json()
        assert body["status"] == "deleted"
        deleted = body["records_deleted"]
        assert deleted.get("classes", 0) >= 1
        assert deleted.get("professors", 0) >= 1
        assert isinstance(body["lines_edited"], int)
        assert body["lines_edited"] >= 2


# ── Presentation enrichment ───────────────────────────────────────────────


class TestPresentationEnrichment:
    def test_presentations_include_student_names(self, client, h, db):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        sym_id = resp.json()["symposium_id"]

        resp = client.post(
            "/api/events/add_department",
            json={
                "symposium_id": sym_id,
                "department_name": "Chem",
                "department_head_name": "Dr. C",
                "email": "c@hamilton.edu",
            },
            headers=h,
        )
        dept_id = resp.json()["department_id"]

        resp = client.post(
            "/api/events/add_class",
            json={
                "name": "CHEM201",
                "department_id": dept_id,
                "professors": [{"name": "Dr. Lee", "email": "lee@hamilton.edu"}],
            },
            headers=h,
        )
        class_id = resp.json()["class_id"]

        client.post(
            "/api/events/add_students",
            json={
                "class_id": class_id,
                "students": [
                    {"name": "Carol", "email": "carol@hamilton.edu"},
                    {"name": "Dave", "email": "dave@hamilton.edu"},
                ],
            },
            headers=h,
        )
        student_ids = [str(r["id"]) for r in db.rows("students")]

        client.post(
            "/api/events/add_presentation",
            json={
                "title": "Polymer Study",
                "class_id": class_id,
                "minutes": 15,
                "buffer": 0,
                "presenting_students": student_ids,
            },
            headers=h,
        )

        resp = client.get("/api/events/presentations", headers=h)
        assert resp.status_code == 200
        presentations = resp.json()["data"]
        assert len(presentations) == 1
        ps = presentations[0]["presenting_students"]
        assert len(ps) == 2
        names = {s["name"] for s in ps}
        assert names == {"Carol", "Dave"}

    def test_presentations_empty_when_no_data(self, client, h, db):
        resp = client.get("/api/events/presentations", headers=h)
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ── Student update persistence ────────────────────────────────────────────


class TestStudentUpdatePersistence:
    def test_update_student_persists(self, client, h, db):
        resp = client.post(
            "/api/events/add_symposium",
            json={"symposium_name": "S", "rooms_available": 1, "default_buffer": 0, "timeframes": [TF_1]},
            headers=h,
        )
        sym_id = resp.json()["symposium_id"]

        resp = client.post(
            "/api/events/add_department",
            json={
                "symposium_id": sym_id,
                "department_name": "CS",
                "department_head_name": "Dr. H",
                "email": "h@hamilton.edu",
            },
            headers=h,
        )
        dept_id = resp.json()["department_id"]

        resp = client.post(
            "/api/events/add_class",
            json={
                "name": "CS101",
                "department_id": dept_id,
                "professors": [{"name": "Prof", "email": "prof@hamilton.edu"}],
            },
            headers=h,
        )
        class_id = resp.json()["class_id"]

        client.post(
            "/api/events/add_students",
            json={
                "class_id": class_id,
                "students": [{"name": "Eve", "email": "eve@hamilton.edu"}],
            },
            headers=h,
        )
        student_id = str(db.rows("students")[0]["id"])

        pres_resp = client.post(
            "/api/events/add_presentation",
            json={
                "title": "Talk",
                "class_id": class_id,
                "minutes": 10,
                "buffer": 0,
                "presenting_students": [student_id],
            },
            headers=h,
        )
        pres_id = pres_resp.json()["presentation_id"]

        resp = client.put(
            "/api/events/update_student",
            json={
                "student_id": student_id,
                "name": "Eve Updated",
                "email": "eve2@hamilton.edu",
                "class_id": class_id,
                "presentation_id": pres_id,
            },
            headers=h,
        )
        assert resp.status_code == 200

        row = db.rows("students")[0]
        assert row["name"] == "Eve Updated"
        assert row["email"] == "eve2@hamilton.edu"
