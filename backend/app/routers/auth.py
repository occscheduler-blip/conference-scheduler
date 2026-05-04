import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Any, cast

from app.auth.dependencies import require_jwt
from app.auth.email import send_otp_email
from app.auth.jwt_utils import JWTClaims, encode_jwt
from app.auth.otp import generate_otp, store_otp, verify_and_consume_otp
from app.auth.password import hash_password, verify_password
from app.supabase_io.client import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Roles that can sign in via OTP (admins use password login instead)
_OTP_ROLES = {"department_head", "professor", "student", "attendee"}

# Which table to look up the email in for each role
_ROLE_TABLE: dict[str, str] = {
    "department_head": "departments",
    "professor": "professors",
    "student": "students",
    "attendee": "attendees",
}

class LoginRequest(BaseModel):
    email: str
    password: str


class CreateAdminRequest(BaseModel):
    email: str
    password: str


class UpdateAdminRequest(BaseModel):
    email: str


@router.post("/admin/login")
def admin_login(body: LoginRequest) -> dict[str, str]:
    logger.info("Admin login attempt for email=%s", body.email)
    resp = supabase.table("admins").select("*").eq("email", body.email).execute()
    rows = cast(list[dict[str,object]], resp.data or [])

    if not rows or not verify_password(body.password, str(rows[0]["password_hash"])):
        logger.warning("Admin login failed for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    admin = rows[0]
    token = encode_jwt(str(admin["id"]), str(admin["email"]), "admin")
    logger.info("Admin login successful for email=%s  admin_id=%s", body.email, admin["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "admin",
        "entity_id": str(admin["id"]),
    }


@router.post("/admin/create")
def admin_create(
    body: CreateAdminRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str]:
    password_hash = hash_password(body.password)
    logger.info("Creating new admin with email=%s", body.email)
    resp = (
        supabase.table("admins")
        .insert({"email": body.email, "password_hash": password_hash})
        .execute()
    )
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        logger.error("Failed to create admin for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create admin.",
        )
    logger.info("Admin created: admin_id=%s  email=%s", rows[0]["id"], body.email)
    return {"admin_id": str(rows[0]["id"])}


@router.get("/admin/list")
def admin_list(
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> list[dict[str, str]]:
    resp = supabase.table("admins").select("id, email").order("email").execute()
    rows = cast(list[dict[str, object]], resp.data or [])
    return [{"id": str(row["id"]), "email": str(row["email"])} for row in rows]


@router.put("/admin/{admin_id}", status_code=status.HTTP_200_OK)
def admin_update(
    admin_id: str,
    body: UpdateAdminRequest,
    _claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str]:
    trimmed = body.email.strip().lower()
    resp = (
        supabase.table("admins")
        .update({"email": trimmed})
        .eq("id", admin_id)
        .execute()
    )
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin not found.",
        )
    return {"admin_id": admin_id, "email": trimmed}


@router.delete("/admin/{admin_id}", status_code=status.HTTP_200_OK)
def admin_delete(
    admin_id: str,
    claims: JWTClaims = Depends(require_jwt(required_roles=["admin"])),
) -> dict[str, str]:
    if admin_id == claims.sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account.",
        )
    supabase.table("admins").delete().eq("id", admin_id).execute()
    return {"deleted_id": admin_id}


# ---------------------------------------------------------------------------
# Attendee self-registration
# ---------------------------------------------------------------------------

class AttendeeRegisterBody(BaseModel):
    email: str


@router.post("/attendee/session", status_code=status.HTTP_200_OK)
def attendee_session() -> dict[str, str]:
    """Create an anonymous attendee identity for public-site viewers."""
    attendee_id = uuid4()
    email = f"anonymous-{attendee_id}@attendee.local"
    insert_resp = supabase.table("attendees").insert({"id": str(attendee_id), "email": email}).execute()
    insert_rows = cast(list[dict[str, object]], insert_resp.data or [])
    if not insert_rows:
        logger.error("Failed to create anonymous attendee session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create attendee session.",
        )

    token = encode_jwt(str(attendee_id), email, "attendee")
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "attendee",
        "entity_id": str(attendee_id),
    }


@router.post("/attendee/register", status_code=status.HTTP_200_OK)
def attendee_register(body: AttendeeRegisterBody) -> dict[str, str]:
    """Register a new attendee (or retrieve existing) and send them an OTP.

    If the email already exists in the attendees table the existing record is
    used — no duplicate is created.  Either way an OTP is sent so the caller
    can verify ownership of the email address.
    """
    logger.info("Attendee register: email=%s", body.email)

    email = body.email.strip().lower()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required.",
        )

    # Upsert: insert if new, do nothing if email already exists
    existing = supabase.table("attendees").select("id").eq("email", email).limit(1).execute()
    existing_rows = cast(list[dict[str, object]], existing.data or [])

    if not existing_rows:
        insert_resp = supabase.table("attendees").insert({"email": email}).execute()
        insert_rows = cast(list[dict[str, object]], insert_resp.data or [])
        if not insert_rows:
            logger.error("Failed to create attendee for email=%s", email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create attendee account.",
            )
        logger.info("New attendee created: email=%s", email)
    else:
        logger.info("Returning attendee signed in: email=%s", email)

    code = generate_otp()
    store_otp(email, code, "attendee")
    send_otp_email(email, code)
    logger.info("OTP sent to attendee email=%s", email)

    return {"detail": "OTP sent to your email address."}


# ---------------------------------------------------------------------------
# OTP sign-in (department heads, professors, students)
# ---------------------------------------------------------------------------

class OTPRequestBody(BaseModel):
    email: str
    role: str  # 'department_head' | 'professor' | 'student'


class OTPVerifyBody(BaseModel):
    email: str
    role: str
    otp: str


@router.post("/otp/request")
def otp_request(body: OTPRequestBody) -> dict[str, str]:
    """Generate a 6-digit OTP and email it to the user.

    The email must already exist in the table for the given role.
    """
    logger.info("OTP request: role=%s  email=%s", body.role, body.email)
    if body.role not in _OTP_ROLES:
        logger.warning("OTP request with invalid role=%s  email=%s", body.role, body.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_OTP_ROLES))}",
        )

    table = _ROLE_TABLE[body.role]
    resp = supabase.table(table).select("id").eq("email", body.email).limit(1).execute()
    if not cast(list[dict[str, object]], resp.data or []):
        logger.warning("OTP request for unknown email=%s  role=%s", body.email, body.role)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    code = generate_otp()
    store_otp(body.email, code, body.role)
    send_otp_email(body.email, code)
    logger.info("OTP sent to email=%s  role=%s", body.email, body.role)

    return {"detail": "OTP sent to your email address."}


@router.post("/otp/verify")
def otp_verify(body: OTPVerifyBody) -> dict[str, str]:
    """Exchange a valid OTP for a JWT access token."""
    logger.info("OTP verify: role=%s  email=%s", body.role, body.email)
    if body.role not in _OTP_ROLES:
        logger.warning("OTP verify with invalid role=%s  email=%s", body.role, body.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_OTP_ROLES))}",
        )

    verify_and_consume_otp(body.email, body.otp, body.role)

    table = _ROLE_TABLE[body.role]
    resp = supabase.table(table).select("id").eq("email", body.email).limit(1).execute()
    rows = cast(list[dict[str, object]], resp.data or [])
    if not rows:
        logger.warning("OTP verify: email=%s not found in %s after OTP consumed", body.email, table)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    entity_id = str(rows[0]["id"])
    token = encode_jwt(entity_id, body.email, body.role)
    logger.info("OTP login successful: role=%s  email=%s  entity_id=%s", body.role, body.email, entity_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": body.role,
        "entity_id": entity_id,
    }


# ---------------------------------------------------------------------------
# Attendee itinerary
# ---------------------------------------------------------------------------

@router.get("/attendee/itinerary")
def get_attendee_itinerary(
    claims: JWTClaims = Depends(require_jwt(required_roles=["attendee"])),
) -> list[str]:
    resp = (
        supabase.table("attendee_itinerary")
        .select("presentation_id")
        .eq("attendee_id", claims.sub)
        .execute()
    )
    rows = cast(list[dict[str, object]], resp.data or [])
    return [str(row["presentation_id"]) for row in rows]


@router.get("/attendee/itinerary/details")
def get_attendee_itinerary_details(
    claims: JWTClaims = Depends(require_jwt(required_roles=["attendee"])),
) -> list[dict[str, Any]]:
    # 1. Get bookmarked presentation IDs
    itinerary_resp = (
        supabase.table("attendee_itinerary")
        .select("presentation_id")
        .eq("attendee_id", claims.sub)
        .execute()
    )
    presentation_ids = [row["presentation_id"] for row in cast(list[dict[str, Any]], itinerary_resp.data or [])]
    if not presentation_ids:
        return []

    # 2. Presentations with presenting students
    pres_resp = (
        supabase.table("presentations")
        .select("*, presenting_students(students(*))")
        .in_("id", presentation_ids)
        .execute()
    )
    presentations = cast(list[dict[str, Any]], pres_resp.data or [])
    for p in presentations:
        joined = p.get("presenting_students") or []
        p["presenting_students"] = [
            row["students"] for row in joined
            if isinstance(row, dict) and row.get("students")
        ]

    # 3. Timeframes linked to these presentations
    tf_resp = (
        supabase.table("timeframes")
        .select("*")
        .in_("linked_id", presentation_ids)
        .execute()
    )
    tf_by_presentation = {
        row["linked_id"]: row
        for row in cast(list[dict[str, Any]], tf_resp.data or [])
    }

    # 4. Classes
    class_ids = list({p["class_id"] for p in presentations if p.get("class_id")})
    classes_by_id: dict[str, dict[str, Any]] = {}
    if class_ids:
        cls_resp = supabase.table("classes").select("*").in_("id", class_ids).execute()
        classes_by_id = {row["id"]: row for row in cast(list[dict[str, Any]], cls_resp.data or [])}

    # 5. Departments
    dept_ids = list({c["department_id"] for c in classes_by_id.values() if c.get("department_id")})
    depts_by_id: dict[str, dict[str, Any]] = {}
    if dept_ids:
        dept_resp = supabase.table("departments").select("*").in_("id", dept_ids).execute()
        depts_by_id = {row["id"]: row for row in cast(list[dict[str, Any]], dept_resp.data or [])}

    # 6. Symposiums
    symposium_ids = list({d["symposium_id"] for d in depts_by_id.values() if d.get("symposium_id")})
    symposiums_by_id: dict[str, dict[str, Any]] = {}
    if symposium_ids:
        symp_resp = supabase.table("symposiums").select("*").in_("id", symposium_ids).execute()
        symposiums_by_id = {row["id"]: row for row in cast(list[dict[str, Any]], symp_resp.data or [])}

    # 7. Assemble
    result: list[dict[str, Any]] = []
    for p in presentations:
        class_row = classes_by_id.get(p.get("class_id", ""))
        if not class_row:
            continue
        dept = depts_by_id.get(class_row.get("department_id", ""))
        if not dept:
            continue
        symposium = symposiums_by_id.get(str(dept.get("symposium_id", "")))
        room_names = symposium.get("room_names") if symposium else None
        room_index = p.get("room")
        room_name = None
        if isinstance(room_index, int):
            if isinstance(room_names, list) and room_index < len(room_names):
                saved_room_name = str(room_names[room_index]).strip() if room_names[room_index] is not None else ""
                room_name = saved_room_name or f"Room {room_index + 1}"
            else:
                room_name = f"Room {room_index + 1}"
        tf = tf_by_presentation.get(p["id"])
        presenter_names = [
            f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
            for s in (p.get("presenting_students") or [])
            if isinstance(s, dict)
        ]
        result.append({
            "presentation_id": p["id"],
            "title": (p.get("title") or "").strip() or f"{dept.get('department_name', '')} Presentation",
            "room": room_name,
            "presenter_names": presenter_names,
            "department_name": dept.get("department_name", ""),
            "department_head_name": dept.get("department_head_name", ""),
            "symposium_id": str(dept.get("symposium_id", "")),
            "symposium_name": symposium.get("name", "") if symposium else "",
            "start_time": tf["start_time"] if tf else None,
            "end_time": tf["end_time"] if tf else None,
        })
    return result


@router.post("/attendee/itinerary/{presentation_id}", status_code=status.HTTP_200_OK)
def add_to_itinerary(
    presentation_id: str,
    claims: JWTClaims = Depends(require_jwt(required_roles=["attendee"])),
) -> dict[str, str]:
    supabase.table("attendee_itinerary").upsert({
        "attendee_id": claims.sub,
        "presentation_id": presentation_id,
    }).execute()
    return {"detail": "Added to itinerary."}


@router.delete("/attendee/itinerary/{presentation_id}", status_code=status.HTTP_200_OK)
def remove_from_itinerary(
    presentation_id: str,
    claims: JWTClaims = Depends(require_jwt(required_roles=["attendee"])),
) -> dict[str, str]:
    supabase.table("attendee_itinerary").delete().eq("attendee_id", claims.sub).eq("presentation_id", presentation_id).execute()
    return {"detail": "Removed from itinerary."}
