"""Email-notification endpoints (dept heads, professors, students)."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

import app.routers.request_schemas as request_schemas
from app.auth.dependencies import require_jwt
from app.auth.email import (
    send_dept_head_notification,
    send_professor_notification,
    send_student_notification,
)
from app.auth.jwt_utils import JWTClaims
from app.config import get_settings
from app.supabase_io import read
from app.supabase_io.client import supabase

logger = logging.getLogger(__name__)
router = APIRouter()


def _login_url() -> str:
    settings = get_settings()
    if settings.site_url:
        return settings.site_url
    origins = settings.cors_origins
    return origins[0] if origins else "http://localhost:3000"


def _symposium_name(symposium_id: UUID) -> str:
    resp = (
        supabase.table("symposiums")
        .select("name")
        .eq("id", str(symposium_id))
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        raise HTTPException(status_code=404, detail="Symposium not found.")
    return str(rows[0].get("name") or "the symposium")


@router.post("/email_symposium")
def email_symposium(
    payload: request_schemas.EmailSymposiumRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str | int]:
    try:
        symposium_name = _symposium_name(payload.symposium_id)
        departments = list(
            getattr(read.get_departments(symposium_id=payload.symposium_id), "data", None)
            or []
        )
        emails_sent = 0
        for department in departments:
            if department.get("emailed"):
                continue
            email = str(department.get("email") or "").strip().lower()
            if not email:
                continue
            send_dept_head_notification(
                email,
                str(department.get("department_head_name") or department.get("department_name") or "Department Head"),
                symposium_name,
                _login_url(),
            )
            supabase.table("departments").update({"emailed": True}).eq("id", str(department["id"])).execute()
            emails_sent += 1
        return {"status": "sent", "emails_sent": emails_sent}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("email_symposium failed: symposium_id=%s", payload.symposium_id)
        raise HTTPException(status_code=500, detail=f"Failed to email symposium: {exc}") from exc


@router.post("/email_classes")
def email_classes(
    payload: request_schemas.EmailClassesRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head"])),
) -> dict[str, str | int]:
    try:
        department_resp = (
            supabase.table("departments")
            .select("symposium_id")
            .eq("id", str(payload.department_id))
            .limit(1)
            .execute()
        )
        department_rows = list(getattr(department_resp, "data", None) or [])
        if not department_rows:
            raise HTTPException(status_code=404, detail="Department not found.")
        symposium_name = _symposium_name(UUID(str(department_rows[0]["symposium_id"])))

        classes = list(
            getattr(read.get_classes(department_id=payload.department_id), "data", None)
            or []
        )
        class_ids = [UUID(str(row["id"])) for row in classes if row.get("id")]
        professors = (
            list(getattr(read.get_professors(class_id=class_ids), "data", None) or [])
            if class_ids
            else []
        )
        emails_sent = 0
        for professor in professors:
            if professor.get("emailed"):
                continue
            email = str(professor.get("email") or "").strip().lower()
            if not email:
                continue
            send_professor_notification(
                email,
                str(professor.get("name") or "Professor"),
                symposium_name,
                _login_url(),
            )
            supabase.table("professors").update({"emailed": True}).eq("id", str(professor["id"])).execute()
            emails_sent += 1
        return {"status": "sent", "emails_sent": emails_sent}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("email_classes failed: department_id=%s", payload.department_id)
        raise HTTPException(status_code=500, detail=f"Failed to email classes: {exc}") from exc


@router.post("/email_students")
def email_students(
    payload: request_schemas.EmailStudentsRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin", "department_head", "professor"])),
) -> dict[str, str | int]:
    try:
        presentation_resp = (
            supabase.table("presentations")
            .select("class_id")
            .eq("id", str(payload.presentation_id))
            .limit(1)
            .execute()
        )
        presentation_rows = list(getattr(presentation_resp, "data", None) or [])
        if not presentation_rows:
            raise HTTPException(status_code=404, detail="Presentation not found.")

        class_resp = (
            supabase.table("classes")
            .select("department_id")
            .eq("id", str(presentation_rows[0]["class_id"]))
            .limit(1)
            .execute()
        )
        class_rows = list(getattr(class_resp, "data", None) or [])
        if not class_rows:
            raise HTTPException(status_code=404, detail="Class not found.")

        department_resp = (
            supabase.table("departments")
            .select("symposium_id")
            .eq("id", str(class_rows[0]["department_id"]))
            .limit(1)
            .execute()
        )
        department_rows = list(getattr(department_resp, "data", None) or [])
        if not department_rows:
            raise HTTPException(status_code=404, detail="Department not found.")
        symposium_name = _symposium_name(UUID(str(department_rows[0]["symposium_id"])))

        presenting_rows = list(
            getattr(read.get_presenting_students(presentation_id=payload.presentation_id), "data", None)
            or []
        )
        student_ids = [str(row["student_id"]) for row in presenting_rows if row.get("student_id")]
        student_resp = (
            supabase.table("students").select("*").in_("id", student_ids).execute()
            if student_ids
            else None
        )
        students = list(getattr(student_resp, "data", None) or [])

        emails_sent = 0
        for student in students:
            if student.get("emailed"):
                continue
            email = str(student.get("email") or "").strip().lower()
            if not email:
                continue
            send_student_notification(
                email,
                str(student.get("name") or "Student"),
                symposium_name,
                _login_url(),
            )
            supabase.table("students").update({"emailed": True}).eq("id", str(student["id"])).execute()
            emails_sent += 1
        return {"status": "sent", "emails_sent": emails_sent}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("email_students failed: presentation_id=%s", payload.presentation_id)
        raise HTTPException(status_code=500, detail=f"Failed to email students: {exc}") from exc
