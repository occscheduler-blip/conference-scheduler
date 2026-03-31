"""
Conference scheduling solver using CP-SAT (OR-Tools).

Data assumptions:
- Symposium timeframes: 15-min slots representing when rooms are available.
- Professor/student timeframes: 15-min slots using the same datetimes as symposium slots.
- Presentations need (minutes // 15) consecutive symposium slots.
- A presentation is only schedulable in a slot if ALL of its students AND all
  requested professors are available for every slot the presentation occupies.
"""

from datetime import datetime
from uuid import UUID

from ortools.sat.python import cp_model

from app.supabase_io import read
from app.supabase_io.supabase_schemas import (
    Presentation,
    Professor,
    Request,
    Student,
    Symposium,
    Timeframe,
)

SLOT_MINUTES = 15


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_inputs(symposium_id: UUID) -> tuple[
    Symposium,
    list[Timeframe],                        # sorted symposium slots
    list[Presentation],                     # presentations to schedule
    dict[UUID, set[datetime]],              # student_id  -> available slot starts
    dict[UUID, set[datetime]],              # professor_id -> available slot starts
    dict[UUID, list[UUID]],                 # presentation_id -> [professor_id, ...]
]:
    # --- Symposium ---
    sym_resp = read.get_symposiums()
    symposium = next(
        Symposium(**s) for s in sym_resp.data if str(s["id"]) == str(symposium_id)
    )

    # --- Symposium slots (15-min blocks) ---
    sym_tf_resp = read.get_timeframes(linked_id=symposium_id)
    sym_slots = sorted(
        [Timeframe(**t) for t in sym_tf_resp.data],
        key=lambda t: t.start_time,
    )

    # --- All departments -> classes for this symposium ---
    dept_resp = read.get_departments(symposium_id=symposium_id)
    dept_ids = [d["id"] for d in dept_resp.data]

    class_resp = read.get_classes(department_id=dept_ids)
    class_ids = [c["id"] for c in class_resp.data]

    # --- Presentations ---
    pres_resp = read.get_presentations(class_id=class_ids)
    presentations = [Presentation(**p) for p in pres_resp.data]

    # --- Students per presentation ---
    pres_ids = [p.id for p in presentations]
    ps_resp = read.get_presenting_students(presentation_id=pres_ids)
    pres_to_students: dict[UUID, list[UUID]] = {}
    for row in ps_resp.data:
        pid = UUID(str(row["presentation_id"]))
        sid = UUID(str(row["student_id"]))
        pres_to_students.setdefault(pid, []).append(sid)

    all_student_ids = list({sid for sids in pres_to_students.values() for sid in sids})

    # --- Student availability ---
    student_availability: dict[UUID, set[datetime]] = {}
    if all_student_ids:
        for sid in all_student_ids:
            tf_resp = read.get_timeframes(linked_id=sid)
            student_availability[sid] = {
                Timeframe(**t).start_time for t in tf_resp.data
            }

    # --- Requests: student -> professor (by email) ---
    req_resp = read.get_requests()
    requests = [Request(**r) for r in req_resp.data]

    # Build student_id -> [professor_id] via email lookup
    prof_resp = read.get_professors(class_id=class_ids)
    professors = [Professor(**p) for p in prof_resp.data]
    prof_by_email: dict[str, Professor] = {p.email: p for p in professors}

    student_to_profs: dict[UUID, list[UUID]] = {}
    for req in requests:
        prof = prof_by_email.get(req.email)
        if prof:
            student_to_profs.setdefault(req.student_id, []).append(prof.id)

    # Map presentation -> requested professor ids
    pres_to_profs: dict[UUID, list[UUID]] = {}
    for pres in presentations:
        prof_ids: list[UUID] = []
        for sid in pres_to_students.get(pres.id, []):
            prof_ids.extend(student_to_profs.get(sid, []))
        pres_to_profs[pres.id] = list(set(prof_ids))

    all_prof_ids = list({pid for pids in pres_to_profs.values() for pid in pids})

    # --- Professor availability ---
    professor_availability: dict[UUID, set[datetime]] = {}
    for prof_id in all_prof_ids:
        tf_resp = read.get_timeframes(linked_id=prof_id)
        professor_availability[prof_id] = {
            Timeframe(**t).start_time for t in tf_resp.data
        }

    return (
        symposium,
        sym_slots,
        presentations,
        student_availability,
        professor_availability,
        pres_to_profs,
    )


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def _available_start_indices(
    pres: Presentation,
    sym_slots: list[Timeframe],
    student_ids: list[UUID],
    prof_ids: list[UUID],
    student_availability: dict[UUID, set[datetime]],
    professor_availability: dict[UUID, set[datetime]],
) -> list[int]:
    """Return indices into sym_slots where this presentation can start."""
    num_slots = pres.minutes // SLOT_MINUTES
    valid: list[int] = []

    for i in range(len(sym_slots) - num_slots + 1):
        window = sym_slots[i : i + num_slots]

        # All slots must be consecutive with no gaps
        for j in range(len(window) - 1):
            delta = (window[j + 1].start_time - window[j].start_time).total_seconds()
            if delta != SLOT_MINUTES * 60:
                break
        else:
            # Check every person is available for all slots in the window
            window_times = {s.start_time for s in window}

            everyone_available = all(
                window_times <= student_availability.get(sid, set())
                for sid in student_ids
            ) and all(
                window_times <= professor_availability.get(pid, set())
                for pid in prof_ids
            )

            if everyone_available:
                valid.append(i)

    return valid


def solve(symposium_id: UUID) -> list[dict[str, object]]:
    """
    Run the CP-SAT scheduler for the given symposium.

    Returns a list of dicts:
        [{"presentation_id": UUID, "start_time": datetime, "end_time": datetime}, ...]

    Raises ValueError if no feasible schedule exists.
    """
    (
        symposium,
        sym_slots,
        presentations,
        student_availability,
        professor_availability,
        pres_to_profs,
    ) = fetch_inputs(symposium_id)

    # Fetch presenting students per presentation
    pres_ids = [p.id for p in presentations]
    ps_resp = read.get_presenting_students(presentation_id=pres_ids)
    pres_to_students: dict[UUID, list[UUID]] = {}
    for row in ps_resp.data:
        pid = UUID(str(row["presentation_id"]))
        sid = UUID(str(row["student_id"]))
        pres_to_students.setdefault(pid, []).append(sid)

    model = cp_model.CpModel()

    # starts[pres_id][slot_index] = BoolVar: does this presentation start at this slot?
    starts: dict[UUID, dict[int, cp_model.IntVar]] = {}

    for pres in presentations:
        num_slots = pres.minutes // SLOT_MINUTES
        student_ids = pres_to_students.get(pres.id, [])
        prof_ids = pres_to_profs.get(pres.id, [])

        valid_indices = _available_start_indices(
            pres,
            sym_slots,
            student_ids,
            prof_ids,
            student_availability,
            professor_availability,
        )

        if not valid_indices:
            raise ValueError(
                f"No valid time slot for presentation '{pres.title}' (id={pres.id}). "
                "Check that all students and professors have submitted availability."
            )

        starts[pres.id] = {
            i: model.new_bool_var(f"starts_{pres.id}_{i}")
            for i in valid_indices
        }

        # Each presentation starts exactly once
        model.add_exactly_one(starts[pres.id].values())

    # Room capacity: at most rooms_available presentations overlap any slot
    for slot_idx in range(len(sym_slots)):
        occupying = []
        for pres in presentations:
            num_slots = pres.minutes // SLOT_MINUTES
            for start_idx, var in starts[pres.id].items():
                if start_idx <= slot_idx < start_idx + num_slots:
                    occupying.append(var)
        if occupying:
            model.add(sum(occupying) <= symposium.rooms_available)

    solver = cp_model.CpSolver()
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError(
            "No feasible schedule found. There may not be enough room/time slots "
            "for all presentations given everyone's availability."
        )

    # Extract results
    results = []
    for pres in presentations:
        num_slots = pres.minutes // SLOT_MINUTES
        for start_idx, var in starts[pres.id].items():
            if solver.value(var):
                start_slot = sym_slots[start_idx]
                end_slot = sym_slots[start_idx + num_slots - 1]
                results.append({
                    "presentation_id": pres.id,
                    "start_time": start_slot.start_time,
                    "end_time": end_slot.end_time,
                })
                break

    return results
