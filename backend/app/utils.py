from datetime import datetime, timezone
from uuid import UUID

from postgrest.base_request_builder import APIResponse


def force_uuid(id: object) -> UUID:
    if isinstance(id, str):
        return UUID(id)
    elif isinstance(id, UUID):
        return id
    else:
        raise ValueError(f"Invalid UUID: {id}")


def ensure_app_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_app_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return ensure_app_timezone(value)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ensure_app_timezone(parsed)
    raise ValueError(f"Invalid datetime value: {value!r}")


def rows_affected(
    response: APIResponse | dict[str, object] | None, fallback: int = 0
) -> int:
    """Return rows affected from a Supabase response object or dict."""
    if response is None:
        return fallback
    if isinstance(response, dict):
        count = response.get("count")
        data = response.get("data")
    else:
        count = getattr(response, "count", None)
        data = getattr(response, "data", None)
    if isinstance(count, int) and count >= 0:
        return count
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return 1
    return fallback
