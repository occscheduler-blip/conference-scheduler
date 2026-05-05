from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ConstraintMode = Literal["off", "soft", "hard"]


@dataclass(frozen=True)
class AvailabilityWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class PresentationInput:
    id: str
    title: str
    duration_minutes: int
    buffer_minutes: int = 0
    class_id: str = ""
    department_id: str = ""
    resource_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleConstraints:
    room_conflicts: ConstraintMode = "hard"
    person_conflicts: ConstraintMode = "hard"
    symposium_windows: ConstraintMode = "hard"
    professor_availability: ConstraintMode = "hard"
    student_availability: ConstraintMode = "hard"
    same_class_same_room: ConstraintMode = "hard"
    slot_alignment: int = 1  # slot size in minutes (1, 5, 10, 15, 20)
    minimize_makespan: ConstraintMode = "soft"
    minimize_department_span: ConstraintMode = "soft"
    minimize_class_span: ConstraintMode = "soft"
    minimize_professor_span: ConstraintMode = "soft"
    balance_rooms: ConstraintMode = "soft"


@dataclass(frozen=True)
class ScheduleProblem:
    symposium_id: str
    rooms_available: int
    symposium_windows: tuple[AvailabilityWindow, ...]
    presentations: tuple[PresentationInput, ...]
    resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = field(
        default_factory=dict
    )
    soft_resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = field(
        default_factory=dict
    )
    professor_resource_ids: tuple[str, ...] = ()
    # Maps a row-level resource_id (e.g. UUID of a students/professors row) to a
    # canonical person identity key (e.g. lowercased email). When two rows share
    # an identity — a double-major student listed in two classes, or a professor
    # cross-listed across classes — both row-ids point to the same key so that
    # downstream solvers can treat them as the same person. Defaults to identity
    # mapping (row-id maps to itself) when the build step has no identity info.
    resource_identity: dict[str, str] = field(default_factory=dict)
    # Display name for each resource_id, used by the verification sweep to phrase
    # cross-block conflict messages without re-reading the DB.
    resource_name: dict[str, str] = field(default_factory=dict)
    slot_minutes: int = 5
    constraints: ScheduleConstraints = field(default_factory=ScheduleConstraints)


@dataclass(frozen=True)
class ScheduledPresentation:
    presentation_id: str
    room_index: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ClassBlock:
    """A contiguous bundle of one class's presentations to be placed atomically.

    The hierarchical scheduler treats each block as a single super-presentation in
    its phase-2 CP-SAT model: pick one (start, room) per block, ensure no overlap
    in the room, then expand back to individual presentations in phase 3.

    For a class whose total_minutes exceeds the longest contiguous symposium
    window, phase-1 splits the class into multiple sub-blocks that share a
    `class_id`; phase-2 then constrains them to land in the same room.
    """
    id: str
    class_id: str
    presentation_ids: tuple[str, ...]  # already ordered for in-block layout
    total_minutes: int  # sum of durations + intra-block buffers
    allowed_windows: tuple[AvailabilityWindow, ...]
    resource_identities: frozenset[str] = frozenset()  # canonical person keys


@dataclass(frozen=True)
class PlacedBlock:
    """Output of phase 2: a class block with its chosen room and start time."""
    block: ClassBlock
    room_index: int
    start: datetime


@dataclass(frozen=True)
class ScheduleResult:
    status: str
    assignments: tuple[ScheduledPresentation, ...]
    unscheduled_presentations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    debug_best_assignments: tuple[ScheduledPresentation, ...] = ()