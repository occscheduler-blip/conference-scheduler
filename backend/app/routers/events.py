from io import StringIO
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from supabase_io import delete, write

from app.config import get_settings
from app.supabase_client import get_supabase_client
import app.routers.request_schemas as request_schemas

router = APIRouter(prefix="/events", tags=["events"])
SYMPOSIUM_DATAFRAMES: dict[int, dict[str, pd.DataFrame]] = {}

@router.post("/add_department")
def add_department(payload: request_schemas.AddDepartmentRequest):
    return {
        "status": "Incomplete endpoint, no effect"
    }

@router.post("/add_symposium")
def add_symposium(payload: request_schemas.AddSymposiumRequest):
    """Validate symposium + timeframe data and insert into Supabase tables.

    Args:
        payload (schemas.AddSymposiumRequest): symposium request payload.

    Returns:
        dict[str, Any]: status payload with inserted record counts.
    """
    try:
        cleaned_name = payload.symposium_name.strip()
        if not cleaned_name:
            raise ValueError("Symposium name cannot be empty.")
        if not payload.timeframes:
            raise ValueError("At least one timeframe is required.")

        symposium_table = "symposiums"
        timeframes_table = "timeframes"
        schema = "public"
        symposium_table = write._validate_identifier(symposium_table, "table name")
        timeframes_table = write._validate_identifier(timeframes_table, "table name")
        schema = write._validate_identifier(schema, "schema")

        symposium_id = uuid4()
        created_at = datetime.now(timezone.utc)
        timeframe_models = [
            request_schemas.Timeframes(
                id=uuid4(),
                start_time=timeframe.start_time,
                end_time=timeframe.end_time,
                symposium_id=symposium_id,
            )
            for timeframe in payload.timeframes
        ]

        symposium_records = [
            {
                "id": symposium_id,
                "created_at": created_at,
                "name": cleaned_name,
                "rooms_available": payload.rooms_available,
            }
        ]
        timeframe_records = [
            {
                "id": timeframe.id,
                "start_time": timeframe.start_time,
                "end_time": timeframe.end_time,
                "symposium_id": timeframe.symposium_id,
            }
            for timeframe in timeframe_models
        ]

        db_url = write._resolve_db_url()
        with write._connection(db_url) as conn:
            write.insert_records(
                table_name=symposium_table,
                records=symposium_records,
                schema=schema,
                conn=conn,
            )
            write.insert_records(
                table_name=timeframes_table,
                records=timeframe_records,
                schema=schema,
                conn=conn,
            )

        return {
            "status": "inserted",
            "symposium_id": str(symposium_id),
            "name": cleaned_name,
            "rooms_available": payload.rooms_available,
            "records_inserted": {
                "symposiums": 1,
                "timeframes": len(timeframe_models),
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc