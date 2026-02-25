<<<<<<< HEAD
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID

import pandas as pd
from fastapi import APIRouter, HTTPException
from app.supabase_io import delete, read, write
from app.supabase_io.client import supabase
=======
from io import StringIO
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from supabase_io import delete, write
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)

import app.routers.request_schemas as request_schemas
import app.supabase_io.supabase_schemas as supabase_schemas

router = APIRouter(prefix="/events", tags=["events"])
SYMPOSIUM_DATAFRAMES: dict[int, dict[str, pd.DataFrame]] = {}

<<<<<<< HEAD

def _serialize_update_fields(fields: dict):
    serialized: dict = {}
    for key, value in fields.items():
        if isinstance(value, UUID):
            serialized[key] = str(value)
        else:
            serialized[key] = value
    return serialized


def _rows_affected(response, fallback: int = 0) -> int:
    """Return rows affected from a Supabase response object."""
    if isinstance(response, dict):
        count = response.get("count")
        if isinstance(count, int) and count >= 0:
            return count

        data = response.get("data")
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return 1

        return fallback

    count = getattr(response, "count", None)
    if isinstance(count, int) and count >= 0:
        return count

    data = getattr(response, "data", None)
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return 1

    return fallback


def _normalize_counts(counts: dict[str, int] | None, fallback: dict[str, int]) -> dict[str, int]:
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


@router.post("/add_class")
def add_class(payload: request_schemas.AddClassRequest):
    try:
        class_id = uuid4()
        class_def = supabase_schemas.Class(
            id=class_id, name=payload.name, department_id=payload.department_id
        )
        class_resp = write.insert("classes", [class_def.model_dump()])
        professors = [
            supabase_schemas.Professor(
                id=uuid4(),
                name=professor.name,
                email=professor.email,
                class_id=class_id,
            )
            for professor in payload.professors
        ]
        professors_payload = [professor.model_dump() for professor in professors]
        prof_resp = write.insert("professors", professors_payload)
        class_inserted = _rows_affected(class_resp, fallback=1)
        professors_inserted = _rows_affected(
            prof_resp, fallback=len(professors_payload)
        )
        records_inserted = {
            "classes": class_inserted,
            "professors": professors_inserted,
        }
        return {
            "status": "Inserted",
            "class_id": class_def.id,
            "department_id": class_def.department_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc
=======
def _serialize_db_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _get_table_columns(*, schema: str, table_name: str) -> set[str]:
    db_url = write._resolve_db_url()
    query = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    """
    with write._connection(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (schema, table_name))
            rows = cur.fetchall()
    return {row[0] for row in rows}


def _table_exists(*, schema: str, table_name: str) -> bool:
    db_url = write._resolve_db_url()
    query = """
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = %s AND table_name = %s
    LIMIT 1
    """
    with write._connection(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (schema, table_name))
            return cur.fetchone() is not None


def _pick_existing_table(*, schema: str, candidates: list[str]) -> str | None:
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            table_name = write._validate_identifier(candidate, "table name")
        except ValueError:
            continue
        if table_name in seen:
            continue
        seen.add(table_name)
        if _table_exists(schema=schema, table_name=table_name):
            return table_name
    return None


def _get_table_columns_with_types(*, schema: str, table_name: str) -> list[tuple[str, str]]:
    db_url = write._resolve_db_url()
    query = """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    ORDER BY ordinal_position
    """
    with write._connection(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (schema, table_name))
            rows = cur.fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _resolve_department_column_map(columns: set[str]) -> dict[str, str]:
    def pick(required_key: str, candidates: list[str], *, optional: bool = False) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        if optional:
            return None
        raise HTTPException(
            status_code=500,
            detail=f"Departments table is missing a required column for {required_key} (accepted: {candidates}).",
        )

    id_col = pick("id", ["id"], optional=True)
    if id_col is None:
        raise HTTPException(status_code=500, detail="Departments table must include an 'id' column.")

    symposium_col = pick("symposium", ["symposium", "symposium_id"])
    dept_name_col = pick("department_name", ["department_name", "dept_name"])
    head_name_col = pick("department_head_name", ["department_head_name", "name"])
    email_col = pick("email", ["email"])

    return {
        "id": id_col,
        "symposium": symposium_col,
        "department_name": dept_name_col,
        "department_head_name": head_name_col,
        "email": email_col,
    }


def _department_table_info() -> tuple[str, str, dict[str, str]]:
    settings = get_settings()
    table_name = write._validate_identifier(settings.supabase_departments_table, "table name")
    schema = write._validate_identifier("public", "schema")
    columns = _get_table_columns(schema=schema, table_name=table_name)
    if not columns:
        raise HTTPException(status_code=500, detail=f"Departments table not found: {schema}.{table_name}")
    mapping = _resolve_department_column_map(columns)
    return schema, table_name, mapping


def _symposium_table_info() -> tuple[str, str, str]:
    settings = get_settings()
    schema = write._validate_identifier("public", "schema")

    symposium_table = _pick_existing_table(
        schema=schema,
        candidates=[
            settings.supabase_symposiums_table,
            settings.supabase_events_table,
            "symposiums",
            "symposium",
            "events",
        ],
    ) or write._validate_identifier(settings.supabase_symposiums_table, "table name")

    timeframes_table = _pick_existing_table(
        schema=schema,
        candidates=[
            settings.supabase_timeframes_table,
            "timeframes",
            "timeframe",
        ],
    ) or write._validate_identifier(settings.supabase_timeframes_table, "table name")

    return schema, symposium_table, timeframes_table


def _pick_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _symposium_name_column(schema: str, symposium_table: str) -> str:
    columns = _get_table_columns(schema=schema, table_name=symposium_table)
    name_col = _pick_column(columns, ("name", "symposium_name", "title"))
    if name_col is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Symposium table {schema}.{symposium_table} is missing a name column "
                "(expected one of: name, symposium_name, title)."
            ),
        )
    return name_col


def _symposium_created_at_column(schema: str, symposium_table: str) -> str | None:
    columns = _get_table_columns(schema=schema, table_name=symposium_table)
    return _pick_column(columns, ("created_at", "created", "created_on"))


def _serialize_records(rows: list[tuple[Any, ...]], columns: list[str]) -> list[dict[str, Any]]:
    return [{column: _serialize_db_value(value) for column, value in zip(columns, row)} for row in rows]


def _timeframes_symposium_column(schema: str, timeframes_table: str) -> str:
    columns = _get_table_columns(schema=schema, table_name=timeframes_table)
    # Prefer actual FK metadata if available.
    fk_query_to_symposium = """
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = %s
      AND tc.table_name = %s
      AND ccu.table_schema = %s
      AND ccu.table_name = %s
      AND ccu.column_name = 'id'
    LIMIT 1
    """
    fk_query_any = """
    SELECT kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = %s
      AND tc.table_name = %s
      AND ccu.column_name = 'id'
    ORDER BY kcu.ordinal_position
    LIMIT 1
    """
    try:
        db_url = write._resolve_db_url()
        symposium_table = write._validate_identifier(get_settings().supabase_symposiums_table, "table name")
        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(fk_query_to_symposium, (schema, timeframes_table, schema, symposium_table))
                row = cur.fetchone()
                if row and row[0]:
                    fk_col = str(row[0])
                    if fk_col in columns:
                        return fk_col

                # Fallback: any FK-to-id column in timeframes.
                cur.execute(fk_query_any, (schema, timeframes_table))
                row = cur.fetchone()
                if row and row[0]:
                    fk_col = str(row[0])
                    if fk_col in columns:
                        return fk_col
    except Exception:
        # Fallback to heuristic candidates below.
        pass

    for candidate in ("symposium_id", "symposium"):
        if candidate in columns:
            return candidate

    id_like_columns = sorted(column for column in columns if column.endswith("_id") and column != "id")
    if len(id_like_columns) == 1:
        return id_like_columns[0]

    typed_columns = _get_table_columns_with_types(schema=schema, table_name=timeframes_table)
    uuid_like_columns = sorted(
        column_name
        for column_name, data_type in typed_columns
        if column_name != "id" and data_type.lower() == "uuid"
    )
    if len(uuid_like_columns) == 1:
        return uuid_like_columns[0]

    symposium_like_columns = sorted(column for column in columns if "symposium" in column.lower())
    if symposium_like_columns:
        return symposium_like_columns[0]

    raise HTTPException(
        status_code=500,
        detail=(
            f"Timeframes table {schema}.{timeframes_table} is missing symposium reference column "
            "(expected one of: symposium_id, symposium)."
        ),
    )


def _symposium_rooms_column(schema: str, symposium_table: str) -> str | None:
    columns = _get_table_columns(schema=schema, table_name=symposium_table)
    for candidate in ("rooms_available", "rooms"):
        if candidate in columns:
            return candidate
    return None


def _timeframes_time_columns(schema: str, timeframes_table: str) -> tuple[str, str]:
    columns = _get_table_columns(schema=schema, table_name=timeframes_table)

    def pick(candidates: tuple[str, ...], label: str) -> str:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        raise HTTPException(
            status_code=500,
            detail=(
                f"Timeframes table {schema}.{timeframes_table} is missing {label} column "
                f"(expected one of: {', '.join(candidates)})."
            ),
        )

    start_col = pick(("start_time", "start"), "start")
    end_col = pick(("end_time", "end"), "end")
    if start_col == end_col:
        start_fallbacks = sorted(column for column in columns if "start" in column.lower())
        end_fallbacks = sorted(column for column in columns if "end" in column.lower())
        if start_fallbacks and end_fallbacks:
            start_col = start_fallbacks[0]
            end_col = end_fallbacks[0]
    return start_col, end_col


def _delete_child_rows_for_symposium(*, conn: Any, schema: str, symposium_table: str, symposium_id: UUID) -> None:
    """Delete rows in tables that have FK references to symposiums(id)."""
    fk_query = """
    SELECT
      tc.table_schema AS child_schema,
      tc.table_name AS child_table,
      kcu.column_name AS child_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND ccu.table_schema = %s
      AND ccu.table_name = %s
      AND ccu.column_name = 'id'
    """

    with conn.cursor() as cur:
      cur.execute(fk_query, (schema, symposium_table))
      references = cur.fetchall()

      for child_schema, child_table, child_column in references:
          try:
              validated_schema = write._validate_identifier(str(child_schema), "schema")
              validated_table = write._validate_identifier(str(child_table), "table name")
              validated_column = write._validate_identifier(str(child_column), "column name")
          except ValueError:
              continue

          delete_query = f"DELETE FROM {validated_schema}.{validated_table} WHERE {validated_column} = %s"
          cur.execute(delete_query, (str(symposium_id),))


@router.get("/db-status")
def db_status():
    """Quick connectivity + table existence check for backend DB wiring."""
    try:
        settings = get_settings()
        schema, symposium_table, timeframes_table = _symposium_table_info()
        departments_table = write._validate_identifier(settings.supabase_departments_table, "table name")

        db_url = write._resolve_db_url()
        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

                def table_exists(table_name: str) -> bool:
                    cur.execute(
                        "SELECT to_regclass(%s)",
                        (f"{schema}.{table_name}",),
                    )
                    row = cur.fetchone()
                    return bool(row and row[0] is not None)

                tables = {
                    "symposiums": {"name": symposium_table, "exists": table_exists(symposium_table)},
                    "timeframes": {"name": timeframes_table, "exists": table_exists(timeframes_table)},
                    "departments": {"name": departments_table, "exists": table_exists(departments_table)},
                }

        return {"status": "ok", "database_connected": True, "tables": tables}
    except Exception as exc:
        return {"status": "error", "database_connected": False, "detail": str(exc)}


@router.get("/departments")
def list_departments(symposium_id: UUID = Query(...)):
    try:
        schema, table_name, mapping = _department_table_info()
        db_url = write._resolve_db_url()
        query = f"""
        SELECT
            {mapping["id"]} AS id,
            {mapping["symposium"]} AS symposium,
            {mapping["department_name"]} AS department_name,
            {mapping["department_head_name"]} AS department_head_name,
            {mapping["email"]} AS email
        FROM {schema}.{table_name}
        WHERE {mapping["symposium"]} = %s
        ORDER BY {mapping["department_name"]} ASC
        """
        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(symposium_id),))
                rows = cur.fetchall()
                columns = [column.name for column in cur.description]

        departments = _serialize_records(rows, columns)
        return {"departments": departments}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list departments: {exc}") from exc
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)


@router.post("/add_department")
def add_department(payload: request_schemas.AddDepartmentRequest):
    try:
<<<<<<< HEAD
        department = supabase_schemas.Department(
            id=uuid4(),
            department_name=payload.department_name,
            department_head_name=payload.department_head_name,
            email=payload.email,
            symposium_id=payload.symposium_id,
        )

        resp = write.insert("departments", [department.model_dump()])
        departments_inserted = _rows_affected(resp, fallback=1)
        records_inserted = {"departments": departments_inserted}

        return {
            "status": "Inserted",
            "department_id": department.id,
            "symposium_id": department.symposium_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
=======
        schema, table_name, mapping = _department_table_info()
        db_url = write._resolve_db_url()
        record = {
            mapping["id"]: uuid4(),
            mapping["symposium"]: payload.symposium,
            mapping["department_name"]: payload.department_name.strip(),
            mapping["department_head_name"]: payload.department_head_name.strip(),
            mapping["email"]: payload.email.strip().lower(),
        }
        inserted = write.insert_records(table_name=table_name, records=[record], schema=schema, db_url=db_url)
        return {"status": "inserted", "records_inserted": inserted, "department_id": str(record[mapping["id"]])}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to add department: {exc}") from exc


@router.put("/departments/{department_id}")
def update_department(department_id: UUID, payload: request_schemas.UpdateDepartmentRequest):
    try:
        schema, table_name, mapping = _department_table_info()
        db_url = write._resolve_db_url()
        query = f"""
        UPDATE {schema}.{table_name}
        SET
            {mapping["department_name"]} = %s,
            {mapping["department_head_name"]} = %s,
            {mapping["email"]} = %s
        WHERE {mapping["id"]} = %s
        """
        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        payload.department_name.strip(),
                        payload.department_head_name.strip(),
                        payload.email.strip().lower(),
                        str(department_id),
                    ),
                )
                updated_rows = cur.rowcount or 0
        if updated_rows == 0:
            raise HTTPException(status_code=404, detail="Department not found.")
        return {"status": "updated", "rows_affected": updated_rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update department: {exc}") from exc


@router.delete("/departments/{department_id}")
def delete_department(department_id: UUID):
    try:
        schema, table_name, mapping = _department_table_info()
        db_url = write._resolve_db_url()
        query = f"DELETE FROM {schema}.{table_name} WHERE {mapping['id']} = %s"
        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(department_id),))
                deleted_rows = cur.rowcount or 0
        if deleted_rows == 0:
            raise HTTPException(status_code=404, detail="Department not found.")
        return {"status": "deleted", "rows_affected": deleted_rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete department: {exc}") from exc


@router.get("/symposiums")
def list_symposiums():
    """List symposium events for admin selection in Edit Existing Event."""
    try:
        schema, table_name, _ = _symposium_table_info()
        name_col = _symposium_name_column(schema, table_name)
        created_at_col = _symposium_created_at_column(schema, table_name)
        db_url = write._resolve_db_url()
        created_at_select = f"{created_at_col} AS created_at" if created_at_col else "NULL::timestamptz AS created_at"

        query = f"""
        SELECT id, {name_col} AS name, {created_at_select}
        FROM {schema}.{table_name}
        ORDER BY created_at DESC NULLS LAST, name ASC
        """

        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                columns = [column.name for column in cur.description]

        symposiums = _serialize_records(rows, columns)
        return {"symposiums": symposiums}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list symposiums: {exc}") from exc


@router.get("/symposiums/{symposium_id}")
def get_symposium(symposium_id: UUID):
    try:
        schema, symposium_table, timeframes_table = _symposium_table_info()
        name_col = _symposium_name_column(schema, symposium_table)
        created_at_col = _symposium_created_at_column(schema, symposium_table)
        rooms_col = _symposium_rooms_column(schema, symposium_table)
        timeframes_symposium_col = _timeframes_symposium_column(schema, timeframes_table)
        start_col, end_col = _timeframes_time_columns(schema, timeframes_table)
        db_url = write._resolve_db_url()

        rooms_select = f"{rooms_col} AS rooms_available" if rooms_col else "NULL::integer AS rooms_available"
        created_at_select = f"{created_at_col} AS created_at" if created_at_col else "NULL::timestamptz AS created_at"
        symposium_query = f"""
        SELECT id, {name_col} AS name, {rooms_select}, {created_at_select}
        FROM {schema}.{symposium_table}
        WHERE id = %s
        LIMIT 1
        """
        timeframe_query = f"""
        SELECT id, {start_col} AS start_time, {end_col} AS end_time, {timeframes_symposium_col} AS symposium_id
        FROM {schema}.{timeframes_table}
        WHERE {timeframes_symposium_col} = %s
        ORDER BY start_time ASC
        """

        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(symposium_query, (str(symposium_id),))
                symposium_row = cur.fetchone()
                symposium_columns = [column.name for column in cur.description] if cur.description else []

                cur.execute(timeframe_query, (str(symposium_id),))
                timeframe_rows = cur.fetchall()
                timeframe_columns = [column.name for column in cur.description] if cur.description else []

        if symposium_row is None:
            raise HTTPException(status_code=404, detail="Symposium not found.")

        symposium = _serialize_records([symposium_row], symposium_columns)[0]
        timeframes = _serialize_records(timeframe_rows, timeframe_columns)
        return {"symposium": symposium, "timeframes": timeframes}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load symposium: {exc}") from exc


@router.put("/symposiums/{symposium_id}")
def update_symposium(symposium_id: UUID, payload: request_schemas.UpdateSymposiumRequest):
    try:
        cleaned_name = payload.symposium_name.strip()
        if not cleaned_name:
            raise ValueError("Symposium name cannot be empty.")
        if not payload.timeframes:
            raise ValueError("At least one timeframe is required.")
        if payload.rooms_available <= 0:
            raise ValueError("rooms_available must be greater than 0.")

        schema, symposium_table, timeframes_table = _symposium_table_info()
        name_col = _symposium_name_column(schema, symposium_table)
        rooms_col = _symposium_rooms_column(schema, symposium_table)
        timeframes_symposium_col = _timeframes_symposium_column(schema, timeframes_table)
        start_col, end_col = _timeframes_time_columns(schema, timeframes_table)
        db_url = write._resolve_db_url()
        timeframe_records = [
            {
                "id": uuid4(),
                start_col: timeframe.start_time,
                end_col: timeframe.end_time,
                timeframes_symposium_col: symposium_id,
            }
            for timeframe in payload.timeframes
        ]

        if rooms_col:
            symposium_update_query = f"""
            UPDATE {schema}.{symposium_table}
            SET {name_col} = %s, {rooms_col} = %s
            WHERE id = %s
            """
            symposium_update_params: tuple[Any, ...] = (cleaned_name, payload.rooms_available, str(symposium_id))
        else:
            symposium_update_query = f"""
            UPDATE {schema}.{symposium_table}
            SET {name_col} = %s
            WHERE id = %s
            """
            symposium_update_params = (cleaned_name, str(symposium_id))
        delete_timeframes_query = f"DELETE FROM {schema}.{timeframes_table} WHERE {timeframes_symposium_col} = %s"

        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(symposium_update_query, symposium_update_params)
                if (cur.rowcount or 0) == 0:
                    raise HTTPException(status_code=404, detail="Symposium not found.")
                cur.execute(delete_timeframes_query, (str(symposium_id),))
            write.insert_records(
                table_name=timeframes_table,
                records=timeframe_records,
                schema=schema,
                conn=conn,
            )

        return {"status": "updated", "symposium_id": str(symposium_id), "timeframes_inserted": len(timeframe_records)}
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
<<<<<<< HEAD
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc

=======
        raise HTTPException(status_code=500, detail=f"Failed to update symposium: {exc}") from exc


@router.delete("/symposiums/{symposium_id}")
def delete_symposium(symposium_id: UUID):
    try:
        schema, symposium_table, timeframes_table = _symposium_table_info()
        timeframes_symposium_col = _timeframes_symposium_column(schema, timeframes_table)
        db_url = write._resolve_db_url()

        # Best-effort cleanup of related rows before deleting symposium.
        try:
            department_schema, department_table, department_map = _department_table_info()
            delete_departments_query = (
                f"DELETE FROM {department_schema}.{department_table} WHERE {department_map['symposium']} = %s"
            )
        except HTTPException:
            delete_departments_query = None

        delete_timeframes_query = f"DELETE FROM {schema}.{timeframes_table} WHERE {timeframes_symposium_col} = %s"
        delete_symposium_query = f"DELETE FROM {schema}.{symposium_table} WHERE id = %s"

        with write._connection(db_url) as conn:
            with conn.cursor() as cur:
                # Remove all FK-linked rows first to avoid constraint failures.
                _delete_child_rows_for_symposium(
                    conn=conn,
                    schema=schema,
                    symposium_table=symposium_table,
                    symposium_id=symposium_id,
                )
                if delete_departments_query is not None:
                    cur.execute(delete_departments_query, (str(symposium_id),))
                cur.execute(delete_timeframes_query, (str(symposium_id),))
                cur.execute(delete_symposium_query, (str(symposium_id),))
                deleted_rows = cur.rowcount or 0

        if deleted_rows == 0:
            raise HTTPException(status_code=404, detail="Symposium not found.")

        return {"status": "deleted", "symposium_id": str(symposium_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete symposium: {exc}") from exc
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)

@router.post("/add_symposium")
def add_symposium(payload: request_schemas.AddSymposiumRequest):
    """Validate symposium + timeframe data and insert into Supabase tables.

    Args:
        payload (schemas.AddSymposiumRequest): symposium request payload.

    Returns:
        dict[str, Any]: status payload with inserted record counts.
    """
    try:
        symposium_id = payload.symposium_id or uuid4()
        symposium = supabase_schemas.Symposium(
            id=symposium_id,
            name=payload.symposium_name,
            created_at=datetime.now(timezone.utc),
            rooms_available=payload.rooms_available,
        )
        symposium_payload = symposium.model_dump()

<<<<<<< HEAD
        # If the symposium already exists (fixed UUID edit flow), update it instead of failing.
        existing = supabase.table("symposiums").select("id").eq("id", str(symposium_id)).limit(1).execute()
        symposiums_inserted = 0
        symposiums_updated = 0
        if existing.data:
            symposium_update_resp = supabase.table("symposiums").update(
                {
                    "name": symposium_payload["name"],
                    "rooms_available": symposium_payload["rooms_available"],
                }
            ).eq("id", str(symposium_id)).execute()
            symposiums_updated = _rows_affected(symposium_update_resp, fallback=1)
        else:
            symposium_insert_resp = write.insert("symposiums", [symposium_payload])
            symposiums_inserted = _rows_affected(symposium_insert_resp, fallback=1)

        # Replace all existing timeframes for this symposium with the newly submitted set.
        deleted_timeframes = delete.delete_timeframes(symposium_id)
        timeframes = [
            supabase_schemas.Timeframe(
                id=uuid4(),
                linked_id=symposium_id,
                start_time=timeframe.start_time,
                end_time=timeframe.end_time,
            )
            for timeframe in payload.timeframes
        ]
        timeframe_payloads = [item.model_dump() for item in timeframes]
        timeframe_response = write.insert("timeframes", timeframe_payloads)
        timeframes_inserted = _rows_affected(timeframe_response, fallback=len(timeframes))
        records_inserted = {
            "symposiums": symposiums_inserted,
            "timeframes": timeframes_inserted,
        }
        records_updated = {"symposiums": symposiums_updated}
        records_deleted = {"timeframes": deleted_timeframes}
=======
        schema, symposium_table, timeframes_table = _symposium_table_info()
        name_col = _symposium_name_column(schema, symposium_table)
        rooms_col = _symposium_rooms_column(schema, symposium_table)
        timeframes_symposium_col = _timeframes_symposium_column(schema, timeframes_table)
        start_col, end_col = _timeframes_time_columns(schema, timeframes_table)

        symposium_id = uuid4()
        created_at = datetime.now(timezone.utc)

        symposium_record = {
            "id": symposium_id,
            "created_at": created_at,
            name_col: cleaned_name,
        }
        if rooms_col:
            symposium_record[rooms_col] = payload.rooms_available
        symposium_records = [symposium_record]
        timeframe_records = [
            {
                "id": uuid4(),
                start_col: timeframe.start_time,
                end_col: timeframe.end_time,
                timeframes_symposium_col: symposium_id,
            }
            for timeframe in payload.timeframes
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
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)

        return {
            "status": "saved",
            "symposium_id": str(symposium_id),
<<<<<<< HEAD
            "name": payload.symposium_name,
            "records_inserted": records_inserted,
            "records_updated": records_updated,
            "records_deleted": records_deleted,
            "lines_edited": _sum_counts(
                records_inserted, records_updated, records_deleted
            ),
        }
=======
            "name": cleaned_name,
                "rooms_available": payload.rooms_available,
                "records_inserted": {
                    "symposiums": 1,
                    "timeframes": len(timeframe_records),
                },
            }
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
<<<<<<< HEAD
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_students")
def add_students(payload: request_schemas.AddStudentsRequest):
    """Adds a list of students to the students table in the database."""
    try:
        students: list[supabase_schemas.Student] = []
        for student in payload.students:
            students.append(
                supabase_schemas.Student(
                    id=uuid4(),
                    name=student.name,
                    email=student.email,
                    class_id=payload.class_id,
                    presentation_id=None,
                )
            )

        students_payload = [item.model_dump() for item in students]
        response = write.insert("students", students_payload)
        students_inserted = _rows_affected(response, fallback=len(students_payload))
        records_inserted = {"students": students_inserted}
        return {
            "status": "inserted",
            "class_id": str(payload.class_id),
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_presentation")
def add_presentation(payload: request_schemas.AddPresentationRequest):
    try:
        presentation_id = uuid4()
        presentation_payload = {
            "id": presentation_id,
            "title": payload.title,
            "class_id": payload.class_id,
            "minutes": payload.minutes,
        }
        pres_resp = write.insert("presentations", [presentation_payload])

        students: list[supabase_schemas.PresentingStudents] = []
        for student in payload.presenting_students:
            students.append(
                supabase_schemas.PresentingStudents(
                    id=uuid4(), presentation_id=presentation_id, student_id=student
                )
            )
        students_payload = [item.model_dump() for item in students]
        students_resp = (
            write.insert("presenting_students", students_payload)
            if students_payload
            else None
        )

        presentations_inserted = _rows_affected(pres_resp, fallback=1)
        presenting_students_inserted = _rows_affected(
            students_resp, fallback=len(students_payload)
        )

        records_inserted = {
            "presentations": presentations_inserted,
            "presenting_students": presenting_students_inserted,
        }

        return {
            "status": "inserted",
            "presentation_id": presentation_id,
            "class_id": payload.class_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.post("/add_prof_req")
def add_prof_request(payload: request_schemas.AddProfReqRequest):
    try:
        request = supabase_schemas.ProfRequest(
            id=uuid4(),
            student_id=payload.student_id,
            professor_id=payload.professor_id,
        )

        response = write.insert("prof_requests", [request.model_dump()])
        prof_requests_inserted = _rows_affected(response, fallback=1)
        records_inserted = {"prof_requests": prof_requests_inserted}

        return {
            "status": "inserted",
            "student_id": payload.student_id,
            "professor_id": payload.professor_id,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to validate symposium payload: {exc}"
        ) from exc


@router.put("/update_timeframes")
def update_timeframes(payload: request_schemas.UpdateTimeframesRequest):
    try:
        deleted_timeframes = delete.delete_timeframes(payload.linked_id)

        timeframes = [
            supabase_schemas.Timeframe(
                id=uuid4(),
                linked_id=payload.linked_id,
                start_time=timeframe.start_time,
                end_time=timeframe.end_time,
            )
            for timeframe in payload.timeframes
        ]
        timeframe_payload = [item.model_dump() for item in timeframes]
        timeframe_resp = write.insert("timeframes", timeframe_payload)
        timeframes_inserted = _rows_affected(timeframe_resp, fallback=len(timeframe_payload))
        records_deleted = {"timeframes": deleted_timeframes}
        records_inserted = {"timeframes": timeframes_inserted}

        return {
            "status": "updated",
            "linked_id": payload.linked_id,
            "records_deleted": records_deleted,
            "records_inserted": records_inserted,
            "lines_edited": _sum_counts(records_deleted, records_inserted),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to update timeframes: {exc}"
        ) from exc


@router.put("/update_student")
def update_student(payload: request_schemas.UpdateStudentRequest):
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"student_id"},
        )
        update_payload = _serialize_update_fields(updates)
        update_resp = supabase.table("students").update(update_payload).eq(
            "id", str(payload.student_id)
        ).execute()
        records_updated = {
            "students": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        return {
            "status": "updated",
            "student_id": str(payload.student_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update student: {exc}"
        ) from exc


@router.put("/update_class")
def update_class(payload: request_schemas.UpdateClassRequest):
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"class_id"},
        )
        update_payload = _serialize_update_fields(updates)
        update_resp = supabase.table("classes").update(update_payload).eq(
            "id", str(payload.class_id)
        ).execute()
        records_updated = {
            "classes": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        return {
            "status": "updated",
            "class_id": str(payload.class_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to update class: {exc}") from exc


@router.put("/update_symposium")
def update_symposium(payload: request_schemas.UpdateSymposiumRequest):
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"symposium_id"},
        )
        if "symposium_name" in updates:
            updates["name"] = updates.pop("symposium_name")
        update_payload = _serialize_update_fields(updates)
        update_resp = supabase.table("symposiums").update(update_payload).eq(
            "id", str(payload.symposium_id)
        ).execute()
        records_updated = {
            "symposiums": _rows_affected(update_resp, fallback=1 if update_payload else 0)
        }

        return {
            "status": "updated",
            "symposium_id": str(payload.symposium_id),
            "fields_updated": sorted(update_payload.keys()),
            "records_updated": records_updated,
            "lines_edited": _sum_counts(records_updated),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update symposium: {exc}"
        ) from exc


@router.put("/update_presentation")
def update_presentation(payload: request_schemas.UpdatePresentationRequest):
    try:
        updates = payload.model_dump(
            exclude_none=True,
            exclude={"presentation_id", "presenting_students"},
        )
        update_payload = _serialize_update_fields(updates)
        presentations_updated = 0
        presenting_students_deleted = 0
        presenting_students_inserted = 0

        if update_payload:
            presentation_update_resp = supabase.table("presentations").update(
                update_payload
            ).eq(
                "id", str(payload.presentation_id)
            ).execute()
            presentations_updated = _rows_affected(presentation_update_resp)

        if payload.presenting_students is not None:
            presenting_students_delete_resp = supabase.table("presenting_students").delete().eq(
                "presentation_id", str(payload.presentation_id)
            ).execute()
            presenting_students_deleted = _rows_affected(
                presenting_students_delete_resp
            )
            presenting_students_payload = [
                supabase_schemas.PresentingStudents(
                    id=uuid4(),
                    presentation_id=payload.presentation_id,
                    student_id=student_id,
                ).model_dump()
                for student_id in payload.presenting_students
            ]
            if presenting_students_payload:
                presenting_students_insert_resp = write.insert(
                    "presenting_students", presenting_students_payload
                )
                presenting_students_inserted = _rows_affected(
                    presenting_students_insert_resp,
                    fallback=len(presenting_students_payload),
                )

        records_inserted = {"presenting_students": presenting_students_inserted}
        records_deleted = {"presenting_students": presenting_students_deleted}
        records_updated = {"presentations": presentations_updated}

        return {
            "status": "updated",
            "presentation_id": str(payload.presentation_id),
            "fields_updated": sorted(update_payload.keys()),
            "presenting_students_updated": payload.presenting_students is not None,
            "records_inserted": records_inserted,
            "records_deleted": records_deleted,
            "records_updated": records_updated,
            "lines_edited": _sum_counts(
                records_inserted, records_deleted, records_updated
            ),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to update presentation: {exc}"
        ) from exc


@router.get("/symposiums")
def get_symposiums():
    try:
        return read.get_symposiums()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/departments")
def get_departments(symposium_id: UUID | None = None):
    try:
        return read.get_departments(symposium_id=symposium_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get symposiums: {exc}"
        ) from exc


@router.get("/classes")
def get_classes(department_id: UUID | None = None):
    try:
        return read.get_classes(department_id=department_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get classes: {exc}"
        ) from exc


@router.get("/students")
def get_students(class_id: UUID | None = None):
    try:
        return read.get_students(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get students: {exc}"
        ) from exc


@router.get("/presentations")
def get_presentations(class_id: UUID | None = None):
    try:
        return read.get_presentations(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get presentations: {exc}"
        ) from exc


@router.get("/presenting_students")
def get_presenting_students(presentation_id: UUID | None = None):
    try:
        return read.get_presenting_students(presentation_id=presentation_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get presenting students: {exc}"
        ) from exc


@router.get("/professors")
def get_professors(class_id: UUID | None = None):
    try:
        return read.get_professors(class_id=class_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get professors: {exc}"
        ) from exc


@router.get("/timeframes")
def get_timeframes(linked_id: UUID | None = None):
    try:
        return read.get_timeframes(linked_id=linked_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get timeframes: {exc}"
        ) from exc


@router.get("/prof_requests")
def get_prof_requests(student_id: UUID | None = None, professor_id: UUID | None = None):
    try:
        return read.get_prof_requests(student_id=student_id, professor_id=professor_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to get professor requests: {exc}"
        ) from exc


@router.delete("/delete_symposium")
def delete_symposium(symposium_id: UUID):
    try:
        counts = _normalize_counts(
            delete.delete_symposium(symposium_id), {"symposiums": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete symposium: {exc}"
            ) from exc


@router.delete("/delete_department")
def delete_department(department_id: UUID):
    try:
        counts = _normalize_counts(
            delete.delete_department(department_id), {"departments": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete department: {exc}"
            ) from exc
    

@router.delete("/delete_class")
def delete_class(class_id: UUID):
    try:
        counts = _normalize_counts(delete.delete_class(class_id), {"classes": 1})
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete class: {exc}"
            ) from exc
    
@router.delete("/delete_student")
def delete_student(student_id: UUID):
    try:
        counts = _normalize_counts(delete.delete_student(student_id), {"students": 1})
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete student: {exc}"
            ) from exc


@router.delete("/delete_professor")
def delete_professor(professor_id: UUID):
    try:
        counts = _normalize_counts(
            delete.delete_professor(professor_id), {"professors": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete professor: {exc}"
            ) from exc


@router.delete("/delete_presentation")
def delete_presentation(presentation_id: UUID):
    try:
        counts = _normalize_counts(
            delete.delete_presentation(presentation_id), {"presentations": 1}
        )
        return {
            "status": "deleted",
            "records_deleted": counts,
            "lines_edited": _sum_counts(counts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
                status_code=400, detail=f"Failed to delete presentation: {exc}"
            ) from exc
=======
        raise HTTPException(status_code=500, detail=f"Failed to validate symposium payload: {exc}") from exc
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
