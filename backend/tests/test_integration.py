"""Integration tests using the in-memory FakeSupabaseClient.

Unlike the unit tests in test_events_api.py (which use MagicMock), these
tests let real data flow through the full stack:

    HTTP request → FastAPI router → supabase_io → FakeSupabaseClient (in-memory)

This catches bugs that mocks can't: enrichment logic, cascade delete ordering,
upsert branching, and serialisation round-trips.
"""

from uuid import uuid4

import pytest


HEADERS = {"X-API-Key": "test-api-key"}

TF_1 = {"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}
TF_2 = {"start_time": "2026-04-21T13:00:00Z", "end_time": "2026-04-21T16:00:00Z"}


# ===========================================================================
# Symposium lifecycle
# ===========================================================================

class TestSymposiumLifecycle:
    def test_post_and_get_all(self, integration_client, fake_supabase):
        """POST a symposium then GET /symposia — row must be present."""
        resp = integration_client.post(
            "/api/events/add_symposium",
            json={
                "symposium_name": "Spring Symposium",
                "rooms_available": 5,
                "timeframes": [TF_1],
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        symp_id = resp.json()["symposium_id"]

        resp = integration_client.get("/api/events/symposia", headers=HEADERS)
        assert resp.status_code == 200
        symposia = resp.json()["symposia"]
        assert len(symposia) == 1
        assert symposia[0]["id"] == symp_id
        assert symposia[0]["name"] == "Spring Symposium"
        assert symposia[0]["rooms_available"] == 5

    def test_get_by_id_returns_symposium_and_timeframes(self, integration_client, fake_supabase):
        """GET /symposia/{id} returns the symposium row plus its timeframes."""
        resp = integration_client.post(
            "/api/events/add_symposium",
            json={
                "symposium_name": "Fall Symposium",
                "rooms_available": 3,
                "timeframes": [TF_1, TF_2],
            },
            headers=HEADERS,
        )
        symp_id = resp.json()["symposium_id"]

        resp = integration_client.get(f"/api/events/symposia/{symp_id}", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["symposium"]["id"] == symp_id
        assert len(body["timeframes"]) == 2

    def test_get_by_id_not_found(self, integration_client, fake_supabase):
        resp = integration_client.get(
            f"/api/events/symposia/{uuid4()}", headers=HEADERS
        )
        assert resp.status_code == 404

    def test_upsert_same_id_updates_not_duplicates(self, integration_client, fake_supabase):
        """POSTing with the same symposium_id a second time updates — no duplicate rows."""
        symp_id = str(uuid4())
        integration_client.post(
            "/api/events/add_symposium",
            json={
                "symposium_id": symp_id,
                "symposium_name": "Original Name",
                "rooms_available": 2,
                "timeframes": [TF_1],
            },
            headers=HEADERS,
        )
        assert fake_supabase.count("symposia") == 1

        resp = integration_client.post(
            "/api/events/add_symposium",
            json={
                "symposium_id": symp_id,
                "symposium_name": "Updated Name",
                "rooms_available": 10,
                "timeframes": [TF_2],
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200
        # Still only one symposium row — not a duplicate
        assert fake_supabase.count("symposia") == 1
        row = fake_supabase.rows("symposia")[0]
        assert row["name"] == "Updated Name"
        assert row["rooms_available"] == 10

    def test_post_inserts_timeframes(self, integration_client, fake_supabase):
        """Each timeframe window in the payload becomes a row in the timeframes table."""
        integration_client.post(
            "/api/events/add_symposium",
            json={
                "symposium_name": "Multi-slot",
                "rooms_available": 4,
                "timeframes": [TF_1, TF_2],
            },
            headers=HEADERS,
        )
        assert fake_supabase.count("timeframes") == 2


# ===========================================================================
# Timeframe replacement
# ===========================================================================

class TestTimeframeReplacement:
    def test_put_replaces_all_timeframes(self, integration_client, fake_supabase):
        """PUT update_timeframes deletes old slots and inserts the new set."""
        symp_id = str(uuid4())
        # Seed two existing timeframes linked to the symposium
        fake_supabase.seed("timeframes", [
            {"id": str(uuid4()), "linked_id": symp_id, "start_time": TF_1["start_time"], "end_time": TF_1["end_time"]},
            {"id": str(uuid4()), "linked_id": symp_id, "start_time": TF_2["start_time"], "end_time": TF_2["end_time"]},
        ])
        assert fake_supabase.count("timeframes") == 2

        new_tf = {"start_time": "2026-05-01T09:00:00Z", "end_time": "2026-05-01T11:00:00Z"}
        resp = integration_client.put(
            "/api/events/update_timeframes",
            json={"linked_id": symp_id, "timeframes": [new_tf]},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        # Old two deleted, one new inserted
        assert fake_supabase.count("timeframes") == 1
        row = fake_supabase.rows("timeframes")[0]
        assert row["linked_id"] == symp_id
        assert row["start_time"] == "2026-05-01T09:00:00+00:00"


# ===========================================================================
# Class + cascade delete
# ===========================================================================

class TestCascadeDeleteClass:
    def _create_class(self, integration_client: object) -> tuple[str, str]:
        """Helper: POST a class with one professor, return (class_id, dept_id)."""
        dept_id = str(uuid4())
        resp = integration_client.post(  # type: ignore[union-attr]
            "/api/events/add_class",
            json={
                "name": "BIO 101",
                "department_id": dept_id,
                "professors": [{"name": "Dr. Smith", "email": "dsmith@hamilton.edu"}],
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["class_id"], dept_id

    def test_delete_class_removes_class_row(self, integration_client, fake_supabase):
        class_id, _ = self._create_class(integration_client)
        assert fake_supabase.count("classes") == 1

        resp = integration_client.delete(
            f"/api/events/delete_class?class_id={class_id}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert fake_supabase.count("classes") == 0

    def test_delete_class_removes_professors(self, integration_client, fake_supabase):
        class_id, _ = self._create_class(integration_client)
        assert fake_supabase.count("professors") == 1

        integration_client.delete(
            f"/api/events/delete_class?class_id={class_id}", headers=HEADERS
        )
        assert fake_supabase.count("professors") == 0

    def test_delete_class_removes_students(self, integration_client, fake_supabase):
        class_id, _ = self._create_class(integration_client)

        # Add two students to the class
        integration_client.post(
            "/api/events/add_students",
            json={
                "class_id": class_id,
                "students": [
                    {"name": "Alice", "email": "alice@hamilton.edu"},
                    {"name": "Bob", "email": "bob@hamilton.edu"},
                ],
            },
            headers=HEADERS,
        )
        assert fake_supabase.count("students") == 2

        integration_client.delete(
            f"/api/events/delete_class?class_id={class_id}", headers=HEADERS
        )
        assert fake_supabase.count("students") == 0

    def test_delete_class_count_response(self, integration_client, fake_supabase):
        """The response records_deleted dict must include 'classes' and 'professors'."""
        class_id, _ = self._create_class(integration_client)
        resp = integration_client.delete(
            f"/api/events/delete_class?class_id={class_id}", headers=HEADERS
        )
        body = resp.json()
        assert body["status"] == "deleted"
        deleted = body["records_deleted"]
        assert deleted.get("classes", 0) >= 1
        assert deleted.get("professors", 0) >= 1
        assert isinstance(body["lines_edited"], int)
        assert body["lines_edited"] >= 2


# ===========================================================================
# Presentation enrichment
# ===========================================================================

class TestPresentationEnrichment:
    def test_presentations_include_presenting_students(
        self, integration_client, fake_supabase
    ):
        """GET /presentations should return each presentation with a
        ``presenting_students`` list populated from the join tables."""
        dept_id = str(uuid4())

        # Create a class
        class_resp = integration_client.post(
            "/api/events/add_class",
            json={
                "name": "CHEM 201",
                "department_id": dept_id,
                "professors": [{"name": "Dr. Lee", "email": "lee@hamilton.edu"}],
            },
            headers=HEADERS,
        )
        class_id = class_resp.json()["class_id"]

        # Add two students
        integration_client.post(
            "/api/events/add_students",
            json={
                "class_id": class_id,
                "students": [
                    {"name": "Carol", "email": "carol@hamilton.edu"},
                    {"name": "Dave", "email": "dave@hamilton.edu"},
                ],
            },
            headers=HEADERS,
        )
        student_ids = [r["id"] for r in fake_supabase.rows("students")]
        assert len(student_ids) == 2

        # Add a presentation with both students
        pres_resp = integration_client.post(
            "/api/events/add_presentation",
            json={
                "title": "Polymer Study",
                "class_id": class_id,
                "minutes": 15,
                "presenting_students": student_ids,
            },
            headers=HEADERS,
        )
        assert pres_resp.status_code == 200, pres_resp.text

        # GET /presentations — should be enriched
        resp = integration_client.get("/api/events/presentations", headers=HEADERS)
        assert resp.status_code == 200
        presentations = resp.json()["data"]
        assert len(presentations) == 1

        ps = presentations[0]["presenting_students"]
        assert len(ps) == 2
        names = {s["name"] for s in ps}
        assert names == {"Carol", "Dave"}

    def test_presentations_empty_when_no_data(self, integration_client, fake_supabase):
        resp = integration_client.get("/api/events/presentations", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ===========================================================================
# Student update
# ===========================================================================

class TestStudentUpdate:
    def test_update_student_persists_to_db(self, integration_client, fake_supabase):
        """PUT update_student actually mutates the in-memory row."""
        class_id = str(uuid4())
        integration_client.post(
            "/api/events/add_students",
            json={
                "class_id": class_id,
                "students": [{"name": "Eve", "email": "eve@hamilton.edu"}],
            },
            headers=HEADERS,
        )
        student_id = fake_supabase.rows("students")[0]["id"]
        pres_id = str(uuid4())
        new_class_id = str(uuid4())

        resp = integration_client.put(
            "/api/events/update_student",
            json={
                "student_id": student_id,
                "name": "Eve Updated",
                "email": "eve2@hamilton.edu",
                "class_id": new_class_id,
                "presentation_id": pres_id,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200

        row = fake_supabase.rows("students")[0]
        assert row["name"] == "Eve Updated"
        assert row["email"] == "eve2@hamilton.edu"
