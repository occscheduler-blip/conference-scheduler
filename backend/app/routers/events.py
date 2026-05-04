"""Aggregator for the /events/* API surface.

The handlers live in domain-specific sibling modules (`events_symposiums`,
`events_departments`, `events_classes`, `events_people`, `events_presentations`,
`events_scheduler`, `events_timeframes`, `events_emails`). This module wires
them together under the shared `/events` prefix so `main.py` can continue to
import one `router` from here.
"""
from fastapi import APIRouter

from app.routers import (
    events_classes,
    events_departments,
    events_emails,
    events_people,
    events_presentations,
    events_scheduler,
    events_symposiums,
    events_timeframes,
)

router = APIRouter(prefix="/events", tags=["events"])

router.include_router(events_symposiums.router)
router.include_router(events_departments.router)
router.include_router(events_classes.router)
router.include_router(events_people.router)
router.include_router(events_presentations.router)
router.include_router(events_scheduler.router)
router.include_router(events_timeframes.router)
router.include_router(events_emails.router)
