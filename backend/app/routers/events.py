from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.supabase_client import get_supabase_client

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(limit: int = 10):
    settings = get_settings()

    try:
        supabase = get_supabase_client()
        response = (
            supabase.table(settings.supabase_events_table)
            .select("*")
            .limit(limit)
            .execute()
        )
        return {"data": response.data, "count": len(response.data or [])}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive catch for provider errors
        raise HTTPException(status_code=502, detail=f"Supabase request failed: {exc}") from exc
