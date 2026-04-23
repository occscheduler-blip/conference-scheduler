"""Shared helpers used by the `events_*` sub-routers.

Extracted from the original monolithic `events.py` so that each sub-router
can import just what it needs. These are internal — the underscore prefix
signals "not meant for callers outside the events routers".
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.supabase_io import read
from app.supabase_io.client import supabase
from app.utils import parse_app_datetime


def _parse_uuid_list(value: str | None) -> list[UUID] | None:
    """Parse a query parameter that may be a single UUID or a comma-separated
    list of UUIDs into a list[UUID]. Returns None if empty/missing. Raises
    HTTP 400 on an invalid UUID.
    """
    if value is None:
        return None
    parts = [piece.strip() for piece in value.split(",")]
    parts = [piece for piece in parts if piece]
    if not parts:
        return None
    try:
        return [UUID(piece) for piece in parts]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {exc}") from exc


def _serialize_update_fields(fields: dict[str, object]) -> dict[str, Any]:
    """Convert a dict of model fields into a JSON-serializable form for Supabase
    updates by converting all UUID values to strings.
    """
    serialized: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, UUID):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def _normalize_counts(
    counts: dict[str, int] | None, fallback: dict[str, int]
) -> dict[str, int]:
    if not isinstance(counts, dict):
        return dict(fallback)

    normalized: dict[str, int] = {}
    for key, value in counts.items():
        if isinstance(value, int) and value >= 0:
            normalized[key] = value

    if not normalized:
        return dict(fallback)

    return normalized


def _sum_counts(*groups: dict[str, int]) -> int:
    total = 0
    for group in groups:
        for value in group.values():
            if isinstance(value, int) and value >= 0:
                total += value
    return total


def _load_symposium_windows(symposium_id: UUID) -> tuple[tuple[datetime, datetime], ...]:
    tf_resp = read.get_timeframes(linked_id=symposium_id)
    windows: list[tuple[datetime, datetime]] = []
    for row in list(getattr(tf_resp, "data", None) or []):
        start = parse_app_datetime(row["start_time"])
        end = parse_app_datetime(row["end_time"])
        if end > start:
            windows.append((start, end))
    windows.sort(key=lambda item: item[0])
    return tuple(windows)


def _load_room_names(symposium_id: UUID) -> list[str]:
    resp = (
        supabase.table("symposiums")
        .select("room_names")
        .eq("id", str(symposium_id))
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    room_names = rows[0].get("room_names") if rows else None
    if not isinstance(room_names, list):
        return []
    return [str(name).strip() if name is not None else "" for name in room_names]


def _room_label(room_names: list[str], room: int) -> str:
    if 0 <= room < len(room_names) and room_names[room]:
        return room_names[room]
    return f"Room {room + 1}"


def _assert_within_symposium_windows(
    symposium_id: UUID,
    start: datetime,
    end: datetime,
) -> None:
    windows = _load_symposium_windows(symposium_id)
    if any(start >= window_start and end <= window_end for window_start, window_end in windows):
        return
    raise HTTPException(
        status_code=409,
        detail="Presentation falls outside the symposium hours.",
    )
