"""Shared primitives for schedule-conflict detection.

Both `PUT /update_schedule_assignment` (single-presentation edit) and
`PUT /bulk_update_schedule_assignments` (multi-presentation edit) answer
the same question: given a candidate (presentation, room, start, end)
does it collide with any other assignment on either the room or any
shared resource (professor/student)?

The loading + indexing work is identical between the two handlers, so
it lives here. Each handler still owns the loop that drives the check,
because bulk does all-pairs over an "effective schedule" dict whereas
single does one-target-against-all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.supabase_io import read


# ── Data loading ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SymposiumEntities:
    """Raw rows for every department/class/presentation/professor under a symposium."""
    departments: list[dict[str, Any]]
    classes: list[dict[str, Any]]
    presentations: list[dict[str, Any]]
    professors: list[dict[str, Any]]


def load_symposium_entities(symposium_id: UUID) -> SymposiumEntities:
    """Fetch everything needed to detect conflicts under one symposium.

    Follows departments → classes → (presentations, professors). Presentations
    come enriched with their `presenting_students` join rows.
    """
    departments_resp = read.get_departments(symposium_id=symposium_id)
    departments = list(getattr(departments_resp, "data", None) or [])
    department_ids = [UUID(str(d["id"])) for d in departments if d.get("id")]

    all_classes: list[dict[str, Any]] = []
    if department_ids:
        classes_resp = read.get_classes(department_id=department_ids)
        all_classes = list(getattr(classes_resp, "data", None) or [])
    class_ids = [UUID(str(c["id"])) for c in all_classes if c.get("id")]

    all_presentations: list[dict[str, Any]] = []
    all_professors: list[dict[str, Any]] = []
    if class_ids:
        pres_resp = read.get_presentations(class_id=class_ids)
        all_presentations = list(getattr(pres_resp, "data", None) or [])
        prof_resp = read.get_professors(class_id=class_ids)
        all_professors = list(getattr(prof_resp, "data", None) or [])

    return SymposiumEntities(
        departments=departments,
        classes=all_classes,
        presentations=all_presentations,
        professors=all_professors,
    )


# ── Index ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConflictIndex:
    """Lookups needed to answer "does X conflict with Y?" efficiently."""
    presentations_by_id: dict[str, dict[str, Any]]
    professors_by_class: dict[str, list[str]]
    all_professor_ids: frozenset[str]
    person_name_by_id: dict[str, str] = field(default_factory=dict)

    def resources_for(self, presentation: dict[str, Any]) -> set[str]:
        """Return the set of person-ids required for this presentation.

        Mirrors the scheduler's resource model: every professor in the
        presentation's class plus every presenting student.
        """
        class_id = str(presentation.get("class_id", ""))
        resources: set[str] = set(self.professors_by_class.get(class_id, []))
        for s in presentation.get("presenting_students", []):
            sid = str(s.get("id", s.get("student_id", "")))
            if sid:
                resources.add(sid)
        return resources

    def person_role(self, person_id: str) -> str:
        """"Professor" if this id belongs to a professor, else "Student"."""
        return "Professor" if person_id in self.all_professor_ids else "Student"

    def person_name(self, person_id: str, fallback: str = "Someone") -> str:
        return self.person_name_by_id.get(person_id, fallback)


def build_conflict_index(entities: SymposiumEntities) -> ConflictIndex:
    """Derive lookup tables from the raw rows returned by `load_symposium_entities`."""
    professors_by_class: dict[str, list[str]] = {}
    person_name_by_id: dict[str, str] = {}
    all_professor_ids: set[str] = set()

    for prof in entities.professors:
        cid = str(prof.get("class_id", ""))
        pid = str(prof.get("id", ""))
        if cid and pid:
            professors_by_class.setdefault(cid, []).append(pid)
            all_professor_ids.add(pid)
            name = str(prof.get("name", "")).strip()
            if name:
                person_name_by_id[pid] = name

    # Eagerly collect student names from every presentation's presenting_students
    # join rows. The handlers used to do this lazily inside the scan loop, which
    # meant the error message could say "Someone" if the student happened to be
    # on the target presentation but not yet seen during iteration.
    for pres in entities.presentations:
        for s in pres.get("presenting_students", []):
            sid = str(s.get("id", s.get("student_id", "")))
            if not sid:
                continue
            name = str(s.get("name", "")).strip()
            if name:
                person_name_by_id[sid] = name

    presentations_by_id: dict[str, dict[str, Any]] = {
        str(p["id"]): p for p in entities.presentations if p.get("id")
    }

    return ConflictIndex(
        presentations_by_id=presentations_by_id,
        professors_by_class=professors_by_class,
        all_professor_ids=frozenset(all_professor_ids),
        person_name_by_id=person_name_by_id,
    )


# ── Message formatters ────────────────────────────────────────────────────
#
# Kept here so both handlers phrase conflicts identically.


def format_room_conflict_single(room_label: str, other_title: str) -> str:
    return (
        f"Room conflict: {room_label} is already occupied by "
        f"\"{other_title}\" at that time."
    )


def format_room_conflict_pair(room_label: str, title_a: str, title_b: str) -> str:
    return (
        f"Room conflict: {room_label} is double-booked between "
        f"\"{title_a}\" and \"{title_b}\" at that time."
    )


def format_person_conflict_single(role: str, name: str, other_title: str) -> str:
    return (
        f"Scheduling conflict: {role} \"{name}\" is required at both "
        f"this presentation and \"{other_title}\" at that time. "
        f"They cannot be in two rooms at once."
    )


def format_person_conflict_pair(role: str, name: str, title_a: str, title_b: str) -> str:
    return (
        f"Scheduling conflict: {role} \"{name}\" is required at both "
        f"\"{title_a}\" and \"{title_b}\" at that time. "
        f"They cannot be in two rooms at once."
    )
