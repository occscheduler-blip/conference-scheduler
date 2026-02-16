from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Body, HTTPException
from supabase_io import delete
from typing import Annotated
import re

from app.config import get_settings
from app.supabase_client import get_supabase_client
import app.routers.schemas as schemas

router = APIRouter(prefix="/events", tags=["events"])
SYMPOSIUM_DATAFRAMES: dict[int, dict[str, pd.DataFrame]] = {}


def _to_dataframe(raw: Any, table_name: str) -> pd.DataFrame:
    if isinstance(raw, pd.DataFrame):
        return raw.copy()
    if isinstance(raw, list):
        return pd.DataFrame(raw)
    if isinstance(raw, dict):
        if "columns" in raw and "data" in raw:
            return pd.DataFrame(
                data=raw["data"],
                columns=raw["columns"],
                index=raw.get("index"),
            )
        return pd.DataFrame([raw])
    raise ValueError(f"Table '{table_name}' must be a list, dict, or DataFrame-like payload.")


def _require_columns(df: pd.DataFrame, columns: set[str], table_name: str) -> None:
    missing = columns.difference(df.columns)
    if missing:
        missing_csv = ", ".join(sorted(missing))
        raise ValueError(f"Table '{table_name}' is missing required columns: {missing_csv}.")


def _coerce_optional_availability(records: list[dict[str, Any]]) -> list[tuple[Any, Any]] | None:
    if not records:
        return None
    return [(row["start"], row["end"]) for row in records]


def _build_symposium_from_tables(dataframes: dict[str, pd.DataFrame]) -> dict[str, Any]:
    symposiums_df = dataframes["symposiums"]
    departments_df = dataframes["departments"]
    chairs_df = dataframes["chairs"]
    classes_df = dataframes["classes"]
    professors_df = dataframes["professors"]
    students_df = dataframes["students"]
    presentations_df = dataframes["presentations"]
    availability_df = dataframes["availability"]

    _require_columns(symposiums_df, {"symposium_id", "name"}, "symposiums")
    _require_columns(departments_df, {"department_id", "department_name", "chair_id"}, "departments")
    _require_columns(chairs_df, {"chair_id", "name", "email"}, "chairs")
    _require_columns(classes_df, {"department_id", "class_id", "class_name"}, "classes")
    _require_columns(professors_df, {"class_id", "professor_id", "name", "email"}, "professors")
    _require_columns(
        students_df, {"class_id", "student_id", "name", "email", "prof_request_ids"}, "students"
    )
    _require_columns(
        presentations_df,
        {"class_id", "presentation_id", "title", "minutes", "student_ids", "professor_ids"},
        "presentations",
    )
    _require_columns(availability_df, {"entity_type", "entity_id", "start", "end"}, "availability")

    symposium_rows = symposiums_df.to_dict(orient="records")
    if len(symposium_rows) != 1:
        raise ValueError("Table 'symposiums' must contain exactly one row.")
    symposium_id = symposium_rows[0]["symposium_id"]
    symposium_name = symposium_rows[0]["name"]

    availability_rows = availability_df.to_dict(orient="records")
    prof_availability: dict[int, list[dict[str, Any]]] = {}
    student_availability: dict[int, list[dict[str, Any]]] = {}
    for row in availability_rows:
        entity_type = row["entity_type"]
        entity_id = row["entity_id"]
        if entity_type == "professor":
            prof_availability.setdefault(entity_id, []).append(row)
        elif entity_type == "student":
            student_availability.setdefault(entity_id, []).append(row)

    chairs_by_id = {
        row["chair_id"]: {"id": row["chair_id"], "name": row["name"], "email": row["email"]}
        for row in chairs_df.to_dict(orient="records")
    }

    professors_by_id: dict[int, dict[str, Any]] = {}
    for row in professors_df.to_dict(orient="records"):
        professors_by_id[row["professor_id"]] = {
            "id": row["professor_id"],
            "name": row["name"],
            "email": row["email"],
            "availability": _coerce_optional_availability(
                prof_availability.get(row["professor_id"], [])
            ),
        }

    students_by_id: dict[int, dict[str, Any]] = {}
    for row in students_df.to_dict(orient="records"):
        students_by_id[row["student_id"]] = {
            "id": row["student_id"],
            "name": row["name"],
            "email": row["email"],
            "prof_requests": [
                professors_by_id[professor_id] for professor_id in row.get("prof_request_ids", [])
            ],
            "availability": _coerce_optional_availability(
                student_availability.get(row["student_id"], [])
            ),
        }

    classes_by_department: dict[int, list[dict[str, Any]]] = {}
    for class_row in classes_df.to_dict(orient="records"):
        class_id = class_row["class_id"]
        class_professors = [
            professors_by_id[row["professor_id"]]
            for row in professors_df.to_dict(orient="records")
            if row["class_id"] == class_id
        ]
        class_students = [
            students_by_id[row["student_id"]]
            for row in students_df.to_dict(orient="records")
            if row["class_id"] == class_id
        ]
        class_presentations = []
        for row in presentations_df.to_dict(orient="records"):
            if row["class_id"] != class_id:
                continue
            class_presentations.append(
                {
                    "id": row["presentation_id"],
                    "title": row["title"],
                    "students": [students_by_id[student_id] for student_id in row["student_ids"]],
                    "professors": [
                        professors_by_id[professor_id] for professor_id in row["professor_ids"]
                    ],
                    "minutes": row["minutes"],
                }
            )
        classes_by_department.setdefault(class_row["department_id"], []).append(
            {
                "id": class_id,
                "name": class_row["class_name"],
                "professors": class_professors,
                "students": class_students,
                "presentations": class_presentations,
            }
        )

    departments = []
    for row in departments_df.to_dict(orient="records"):
        departments.append(
            {
                "id": row["department_id"],
                "name": row["department_name"],
                "chair": chairs_by_id[row["chair_id"]],
                "classes": classes_by_department.get(row["department_id"], []),
            }
        )

    return {"id": symposium_id, "name": symposium_name, "departments": departments}

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


@router.post("/add_symposium")
def add_symposium(
    symposium_name: Annotated[
        str,
        Body(
            ...,
            description="Symposium name.",
            openapi_examples={
                "symposium_name": {
                    "summary": "Symposium name payload",
                    "value": "Spring Symposium",
                }
            },
        ),
    ],
    timeframes: Annotated[
        list[tuple[datetime, datetime]],
        Body(
            ...,
            description="List of (start_time, end_time) tuples for symposium availability windows.",
            openapi_examples={
                "timeframes": {
                    "summary": "Two symposium windows",
                    "value": [
                        ["2026-04-20T09:00:00Z", "2026-04-20T12:00:00Z"],
                        ["2026-04-21T13:00:00Z", "2026-04-21T16:00:00Z"],
                    ],
                }
            },
        ),
    ],
):
    """Validate symposium + timeframe data and return write-ready records.

    Args:
        symposium_name (str): symposium name.
        timeframes (list[tuple[datetime, datetime]]): list of start/end time tuples.

    Returns:
        dict[str, Any]: validated payload for `supabase_io.write.write_validated_records`.
    """
    try:
        cleaned_name = symposium_name.strip()
        if not cleaned_name:
            raise ValueError("Symposium name cannot be empty.")
        if not timeframes:
            raise ValueError("At least one timeframe is required.")
        symposium_id = uuid4()
        symposium_model = schemas.Symposium(
            id=symposium_id,
            name=cleaned_name,
            created_at=datetime.now(timezone.utc),
        )
        timeframe_models = [
            schemas.Timeframes(
                id=uuid4(),
                start_time=start_time,
                end_time=end_time,
                symposium_id=symposium_id,
            )
            for start_time, end_time in timeframes
        ]

        symposium_row = symposium_model.model_dump(mode="json")
        timeframe_rows = [timeframe.model_dump(mode="json") for timeframe in timeframe_models]
        return {
            "status": "validated",
            "symposium_id": str(symposium_id),
            "name": cleaned_name,
            "records_by_table": {
                "symposiums": [symposium_row],
                "timeframes": timeframe_rows,
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc


@router.delete("/remove_symposium/{symposium_id}")
def remove_symposium(symposium_id: int, symposium_name: str | None = None):
    """Endpoint for removing a symposium table by id.

    Args:
        symposium_id (int): the symposium id used to derive the table name.
        symposium_name (str | None): explicit table name override.

    Returns:
        dict[str, Any]: status and dropped table name.
    """
    try:
        table_name = symposium_name or f"symposium_{symposium_id}"
        delete.drop_table(
            table_name=table_name,
            schema="public",
        )
        return {"status": "deleted", "symposium_id": symposium_id, "table_dropped": table_name}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete symposium: {exc}") from exc
