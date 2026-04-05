from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AvailabilityWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class PresentationInput:
    id: str
    title: str
    duration_minutes: int
    resource_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleProblem:
    symposium_id: str
    rooms_available: int
    symposium_windows: tuple[AvailabilityWindow, ...]
    presentations: tuple[PresentationInput, ...]
    resource_windows: dict[str, tuple[AvailabilityWindow, ...]] = field(
        default_factory=dict
    )
    slot_minutes: int = 5


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
