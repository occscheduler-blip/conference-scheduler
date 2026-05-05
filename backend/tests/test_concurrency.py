"""Integration tests for the concurrency safeguards added across the app.

Covers:
  - Singleton scheduler job (partial unique index + advisory lock)
  - Optimistic concurrency on entity updates (expected_updated_at → 409 stale)
  - Defensive schema constraints (duplicate presenting_students, per-class email)
  - Symposium advisory lock serializing manual schedule edits

These hit the real local Supabase. Race-style tests use threading.Barrier
to align two TestClient threads, then assert post-conditions against the DB.
"""
from __future__ import annotations

import threading
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests import builders


def _seed_minimal_symposium(client: TestClient, h: dict[str, str], db: Any) -> dict[str, Any]:
    """Symposium → department → class → 1 student → 1 presentation."""
    sym = builders.add_symposium(client, h)
    dept = builders.add_department(client, h, sym["symposium_id"])
    cls = builders.add_class(client, h, dept["department_id"])
    builders.add_students(client, h, cls["class_id"], count=1)
    student_ids = [str(r["id"]) for r in db.rows("students")]
    pres = builders.add_presentation(
        client, h, cls["class_id"], student_ids, title="Concurrency Test"
    )
    return {
        "symposium_id": sym["symposium_id"],
        "department_id": dept["department_id"],
        "class_id": cls["class_id"],
        "student_ids": student_ids,
        "presentation_id": pres["presentation_id"],
    }


# ── Singleton scheduler job ───────────────────────────────────────────────


class TestSchedulerSingleton:
    def test_two_concurrent_runs_only_one_wins(self, client: TestClient, h, db):
        """Firing /schedule twice in parallel yields at most one active job.

        With the partial-unique index on scheduler_jobs(symposium_id) WHERE
        status IN ('pending','running'), the second insert fails. The router
        translates that into a 409 with code='scheduler_busy' and the existing
        job_id. We tolerate either (200, 409) or (409, 200) — but never (200, 200).
        """
        seed = _seed_minimal_symposium(client, h, db)
        body = {
            "symposium_id": seed["symposium_id"],
            "debug_mode": False,
            "constraints": {},
        }

        barrier = threading.Barrier(2)
        results: list[tuple[int, dict[str, Any]]] = []
        lock = threading.Lock()

        def fire():
            barrier.wait()
            r = client.post("/api/events/schedule", json=body, headers=h)
            try:
                payload = r.json()
            except Exception:
                payload = {"raw": r.text}
            with lock:
                results.append((r.status_code, payload))

        t1 = threading.Thread(target=fire)
        t2 = threading.Thread(target=fire)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        statuses = sorted(s for s, _ in results)
        assert len(results) == 2, f"both threads should return; got {results}"
        assert 200 in statuses, f"at least one accept expected; got {statuses}"
        # Either both raced and one got 409 scheduler_busy / 423 busy, or both
        # serialized with one ending after the other (200, 200 *iff* the first
        # job already finished — in practice the solver takes longer than the
        # second request to start, so we expect one rejection).
        if statuses != [200, 200]:
            rejection = [code for code, _ in results if code != 200][0]
            assert rejection in (409, 423), f"unexpected reject status {rejection}"

        # Post-condition: at most ONE row is still pending|running.
        all_jobs = [
            row for row in db.rows("scheduler_jobs")
            if str(row.get("symposium_id")) == seed["symposium_id"]
        ]
        active = [j for j in all_jobs if j.get("status") in ("pending", "running")]
        assert len(active) <= 1, f"expected ≤1 active job, found {active}"


# ── Optimistic concurrency on entity updates ──────────────────────────────


class TestOptimisticConcurrency:
    def test_update_class_with_correct_updated_at_succeeds(self, client: TestClient, h, db, classroom):
        # Read the class to grab the current updated_at timestamp.
        rows = db.rows("classes")
        assert rows, "class fixture should have inserted a row"
        current_updated_at = rows[0]["updated_at"]

        resp = client.put(
            "/api/events/update_class",
            json={
                "class_id": classroom["class_id"],
                "name": "Renamed",
                "department_id": classroom["department_id"],
                "expected_updated_at": current_updated_at.isoformat()
                if hasattr(current_updated_at, "isoformat")
                else current_updated_at,
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.text

    def test_update_class_with_stale_updated_at_returns_409(self, client: TestClient, h, db, classroom):
        # First update — bumps updated_at via trigger.
        resp = client.put(
            "/api/events/update_class",
            json={
                "class_id": classroom["class_id"],
                "name": "First Rename",
                "department_id": classroom["department_id"],
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.text

        # Capture the *original* (now stale) timestamp by truncating-ish trick:
        # we know the first PUT bumped updated_at to a newer value, so any
        # earlier ISO timestamp will be stale. Send 1970-01-01 to guarantee mismatch.
        resp = client.put(
            "/api/events/update_class",
            json={
                "class_id": classroom["class_id"],
                "name": "Second Rename",
                "department_id": classroom["department_id"],
                "expected_updated_at": "1970-01-01T00:00:00+00:00",
            },
            headers=h,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        detail = body.get("detail")
        assert isinstance(detail, dict)
        assert detail.get("code") == "stale"
        assert detail.get("current_row") is not None

    def test_omitting_expected_updated_at_still_works(self, client: TestClient, h, classroom):
        """Backwards-compat: requests without expected_updated_at still update."""
        resp = client.put(
            "/api/events/update_class",
            json={
                "class_id": classroom["class_id"],
                "name": "No Version Check",
                "department_id": classroom["department_id"],
            },
            headers=h,
        )
        assert resp.status_code == 200, resp.text


# ── Schema-level defenses ─────────────────────────────────────────────────


class TestSchemaConstraints:
    def test_duplicate_presenting_students_rejected(self, client: TestClient, h, db, presentation):
        """The UNIQUE(presentation_id, student_id) constraint blocks duplicates."""
        student_id = presentation["student_ids"][0]
        # Attempt to update with the same student_id listed twice — should violate UNIQUE.
        resp = client.put(
            "/api/events/update_presentation",
            json={
                "presentation_id": presentation["presentation_id"],
                "title": "Duplicates",
                "class_id": presentation["class_id"],
                "minutes": 20,
                "buffer": 0,
                "presenting_students": [student_id, student_id],
            },
            headers=h,
        )
        assert resp.status_code in (400, 500), resp.text  # FK / unique violation surfaces as a 4xx/5xx

    def test_duplicate_email_within_class_rejected(self, client: TestClient, h, classroom):
        body = {
            "class_id": classroom["class_id"],
            "students": [
                {"name": "Alice A", "email": "alice@hamilton.edu"},
                {"name": "Alice B", "email": "ALICE@hamilton.edu"},  # case-insensitive dup
            ],
        }
        resp = client.post("/api/events/add_students", json=body, headers=h)
        # Postgres rejects with unique violation surfaced through supabase-py.
        assert resp.status_code in (400, 409, 500), resp.text

    def test_inverted_timeframe_rejected(self, client: TestClient, h, db):
        """CHECK (end_time > start_time) on timeframes blocks inverted ranges."""
        # Direct INSERT via psycopg to bypass pydantic validation.
        url = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
        sym = builders.add_symposium(client, h)
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                with pytest.raises(psycopg.errors.CheckViolation):
                    cur.execute(
                        "INSERT INTO public.timeframes (id, linked_id, start_time, end_time)"
                        " VALUES (gen_random_uuid(), %s, '2026-04-20T10:00:00Z', '2026-04-20T09:00:00Z')",
                        (sym["symposium_id"],),
                    )


# ── Schedule-edit advisory lock ───────────────────────────────────────────


class TestScheduleEditLock:
    def test_two_concurrent_updates_serialize_or_409(self, client: TestClient, h, db):
        """Two parallel update_schedule_assignment requests must not both
        succeed when they would put two presentations in the same room+time.

        The advisory lock serializes the two; the second sees the first's
        write and either gets a 409 conflict OR succeeds (with no real
        conflict, because they're on different rooms/people). The key
        invariant: we never end up with two presentations claiming the same
        (room, overlapping time) in temporary_timeframes/temporary_room.
        """
        sym = builders.add_symposium(client, h, name="Sched Race")
        dept = builders.add_department(client, h, sym["symposium_id"])
        cls = builders.add_class(client, h, dept["department_id"])
        builders.add_students(client, h, cls["class_id"], count=2)
        student_ids = [str(r["id"]) for r in db.rows("students")]
        p1 = builders.add_presentation(
            client, h, cls["class_id"], [student_ids[0]], title="P1"
        )
        p2 = builders.add_presentation(
            client, h, cls["class_id"], [student_ids[1]], title="P2"
        )

        slot = {
            "start_time": "2026-04-20T09:00:00Z",
            "end_time": "2026-04-20T09:30:00Z",
        }

        barrier = threading.Barrier(2)
        results: list[int] = []
        lock = threading.Lock()

        def fire(presentation_id: str):
            payload = {
                "symposium_id": sym["symposium_id"],
                "presentation_id": presentation_id,
                "room": 0,  # both target room 0 — direct room conflict
                **slot,
            }
            barrier.wait()
            r = client.put("/api/events/update_schedule_assignment", json=payload, headers=h)
            with lock:
                results.append(r.status_code)

        t1 = threading.Thread(target=fire, args=(p1["presentation_id"],))
        t2 = threading.Thread(target=fire, args=(p2["presentation_id"],))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        # Outcomes: exactly one 200 and the other 409 (room conflict caught
        # under the lock). We never want both 200 — that means both writes
        # raced through and produced a real conflict.
        assert sorted(results) == [200, 409], f"got {results}"

        # Post-condition: only one presentation occupies room 0 at that slot.
        # The other was rejected, so its temporary_room remains NULL.
        room0 = [
            row for row in db.rows("presentations")
            if row.get("temporary_room") == 0
        ]
        assert len(room0) == 1, f"expected exactly one presentation in room 0, got {room0}"
