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
    slot_minutes: int = 5
    constraints: ScheduleConstraints = field(default_factory=ScheduleConstraints)


@dataclass(frozen=True)
class ScheduledPresentation:
    presentation_id: str
    room_index: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ScheduleResult:
    status: str
    assignments: tuple[ScheduledPresentation, ...]
    unscheduled_presentations: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    relaxations_applied: tuple[str, ...] = ()