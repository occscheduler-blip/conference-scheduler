"""Shared builders for integration tests.

Each test file used to define its own copies of TF_1/TF_2 and a near-identical
set of `_add_symposium` / `_seed_chain` helpers. This module centralises them.

Existing tests import with aliases like:

    from tests.builders import add_symposium as _add_symposium

so callsites don't change. New tests can use the bare names, or — preferably —
the fixtures in `conftest.py` that wrap these builders.
"""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.db_helper import DbHelper

# ── Canonical test timeframes ─────────────────────────────────────────────

TF_1: dict[str, str] = {
    "start_time": "2026-04-20T09:00:00Z",
    "end_time": "2026-04-20T12:00:00Z",
}
TF_2: dict[str, str] = {
    "start_time": "2026-04-21T13:00:00Z",
    "end_time": "2026-04-21T16:00:00Z",
}


# ── Single-entity builders ────────────────────────────────────────────────

def add_symposium(
    client: TestClient,
    h: dict[str, str],
    name: str = "Spring Symposium",
    rooms: int = 5,
    timeframes: list[dict[str, str]] | None = None,
    default_buffer: int = 0,
) -> dict[str, Any]:
    if timeframes is None:
        timeframes = [TF_1, TF_2]
    resp = client.post(
        "/api/events/add_symposium",
        json={
            "symposium_name": name,
            "rooms_available": rooms,
            "default_buffer": default_buffer,
            "timeframes": timeframes,
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def add_department(
    client: TestClient,
    h: dict[str, str],
    symposium_id: str,
    name: str = "Computer Science",
    head_name: str = "Dr. Head",
    email: str = "head@hamilton.edu",
) -> dict[str, Any]:
    resp = client.post(
        "/api/events/add_department",
        json={
            "symposium_id": symposium_id,
            "department_name": name,
            "department_head_name": head_name,
            "email": email,
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def add_class(
    client: TestClient,
    h: dict[str, str],
    department_id: str,
    name: str = "CS101",
    professor_name: str = "Prof. Smith",
    professor_email: str = "psmith@hamilton.edu",
) -> dict[str, Any]:
    resp = client.post(
        "/api/events/add_class",
        json={
            "name": name,
            "department_id": department_id,
            "professors": [{"name": professor_name, "email": professor_email}],
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def add_students(
    client: TestClient,
    h: dict[str, str],
    class_id: str,
    count: int = 2,
) -> dict[str, Any]:
    students = [
        {"name": f"Student {i}", "email": f"student{i}@hamilton.edu"}
        for i in range(count)
    ]
    resp = client.post(
        "/api/events/add_students",
        json={"class_id": class_id, "students": students},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def add_presentation(
    client: TestClient,
    h: dict[str, str],
    class_id: str,
    student_ids: list[str],
    title: str = "Test Presentation",
    minutes: int = 20,
    buffer: int = 0,
) -> dict[str, Any]:
    resp = client.post(
        "/api/events/add_presentation",
        json={
            "title": title,
            "class_id": class_id,
            "minutes": minutes,
            "buffer": buffer,
            "presenting_students": student_ids,
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def add_request(
    client: TestClient,
    h: dict[str, str],
    student_id: str,
    name: str = "Prof. Pref",
    email: str = "pref@hamilton.edu",
) -> dict[str, Any]:
    resp = client.post(
        "/api/events/add_request",
        json={"name": name, "email": email, "student_id": student_id},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Composite seeder ──────────────────────────────────────────────────────

def seed_chain(
    client: TestClient,
    h: dict[str, str],
    db: DbHelper,
    student_count: int = 2,
    with_presentation: bool = False,
    with_request: bool = False,
) -> dict[str, Any]:
    """Build a symposium → department → class → students chain.

    Optionally also create a presentation (using all students) and/or a
    professor request for the first student. Returns a dict with every id
    that was created; callers pluck out whatever they need.
    """
    sym = add_symposium(client, h, name="Symp", rooms=1, timeframes=[TF_1])
    sym_id = sym["symposium_id"]

    dept = add_department(client, h, sym_id, name="CS")
    dept_id = dept["department_id"]

    cls = add_class(client, h, dept_id)
    class_id = cls["class_id"]
    professor_ids = cls["professor_ids"]

    add_students(client, h, class_id, count=student_count)
    student_ids = [str(r["id"]) for r in db.rows("students")]

    result: dict[str, Any] = {
        "symposium_id": sym_id,
        "department_id": dept_id,
        "class_id": class_id,
        "professor_id": professor_ids[0],
        "professor_ids": professor_ids,
        "student_ids": student_ids,
    }

    if with_presentation and student_ids:
        pres = add_presentation(client, h, class_id, student_ids)
        result["presentation_id"] = pres["presentation_id"]

    if with_request and student_ids:
        add_request(client, h, student_ids[0])

    return result
