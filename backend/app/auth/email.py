import logging

import resend

from app.config import get_settings

logger = logging.getLogger(__name__)

_SUBJECT = "Your Conference Scheduler Sign-In Code"
_BODY_TEMPLATE = (
    "<p>Your one-time sign-in code is:</p>"
    "<h2 style='letter-spacing:4px'>{code}</h2>"
    "<p>This code expires in 10 minutes. Do not share it with anyone.</p>"
)


def send_otp_email(to_email: str, otp_code: str) -> None:
    """Send the OTP to *to_email* via Resend.

    If RESEND_API_KEY is not configured, logs the code at WARNING level
    so local development works without email credentials.
    """
    settings = get_settings()

    if not settings.resend_api_key:
        logger.warning("[DEV] OTP for %s: %s", to_email, otp_code)
        return

    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.resend_from,
            "to": [to_email],
            "subject": _SUBJECT,
            "html": _BODY_TEMPLATE.format(code=otp_code),
        }
    )


_DEPT_HEAD_SUBJECT = "You've been invited to Conference Scheduler"
_DEPT_HEAD_BODY = (
    "<p>Hello {name},</p>"
    "<p>You have been added as a department head for <strong>{symposium_name}</strong>.</p>"
    "<p>Please sign in to add your classes and professors:</p>"
    "<p><a href='{login_url}'>{login_url}</a></p>"
)

_PROFESSOR_SUBJECT = "You've been added to Conference Scheduler"
_PROFESSOR_BODY = (
    "<p>Hello {name},</p>"
    "<p>You have been added as a professor for <strong>{symposium_name}</strong>.</p>"
    "<p>Please sign in to upload your students, create presentation groups, and update your availability:</p>"
    "<p><a href='{login_url}'>{login_url}</a></p>"
)

_STUDENT_SUBJECT = "Your presentation has been submitted"
_STUDENT_BODY = (
    "<p>Hello {name},</p>"
    "<p>You have been added to a presentation for <strong>{symposium_name}</strong>.</p>"
    "<p>Please sign in to set your availability preferences:</p>"
    "<p><a href='{login_url}'>{login_url}</a></p>"
)


def _send(to_email: str, subject: str, html: str) -> None:
    """Shared Resend dispatch. Logs in dev if no API key is set."""
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("[DEV] Email to %s | %s", to_email, subject)
        return
    resend.api_key = settings.resend_api_key
    resend.Emails.send({"from": settings.resend_from, "to": [to_email], "subject": subject, "html": html})


def send_dept_head_notification(to_email: str, name: str, symposium_name: str, login_url: str) -> None:
    _send(to_email, _DEPT_HEAD_SUBJECT, _DEPT_HEAD_BODY.format(name=name, symposium_name=symposium_name, login_url=login_url))


def send_professor_notification(to_email: str, name: str, symposium_name: str, login_url: str) -> None:
    _send(to_email, _PROFESSOR_SUBJECT, _PROFESSOR_BODY.format(name=name, symposium_name=symposium_name, login_url=login_url))


def send_student_notification(to_email: str, name: str, symposium_name: str, login_url: str) -> None:
    _send(to_email, _STUDENT_SUBJECT, _STUDENT_BODY.format(name=name, symposium_name=symposium_name, login_url=login_url))
