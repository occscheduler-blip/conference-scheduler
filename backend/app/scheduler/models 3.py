from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ConstraintMode = Literal["off", "soft", "hard"]
RelaxableConstraint = Literal[
    "room_conflicts",
    "person_conflicts",
    "symposium_windows",
    "professor_availability",
    "student_availability",
    "same_class_same_room",
    "slot_alignment",
    "minimize_makespan",
    "minimize_class_span",
    "minimize_professor_span",
    "balance_rooms",
]


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
    resource_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleConstraints:
    room_conflicts: ConstraintMode = "hard"
    person_conflicts: ConstraintMode = "hard"
    symposium_windows: ConstraintMode = "hard"
    professor_availability: ConstraintMode = "hard"
    student_availability: ConstraintMode = "hard"
    same_class_same_room: ConstraintMode = "hard"
    slot_alignment: ConstraintMode = "hard"
    minimize_makespan: ConstraintMode = "soft"
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
    resource_names: dict[str, str] = field(default_factory=dict)
    slot_minutes: int = 5
    constraints: ScheduleConstraints = field(default_factory=ScheduleConstraints)


@dataclass(frozen=True)
class ScheduledPresentation:
    presentation_id: str
    room_index: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ScheduleConflictInsight:
    presentation_id: str
    presentation_title: str
    conflict_type: str
    message: str
    suggested_fix: str = ""
    recommended_constraint: RelaxableConstraint | None = None
    blocking_entity_ids: tuple[str, ...] = ()
    blocking_entity_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConstraintRelaxationSuggestion:
    constraint: RelaxableConstraint
    reason: str
    affected_entity_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleResult:
    status: str
    assignments: tuple[ScheduledPresentation, ...]
    unscheduled_presentations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    relaxations_applied: tuple[str, ...] = ()
    conflict_insights: tuple[ScheduleConflictInsight, ...] = ()
    recommended_relaxations: tuple[ConstraintRelaxationSuggestion, ...] = ()
