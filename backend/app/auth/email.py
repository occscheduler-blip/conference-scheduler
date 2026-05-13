import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

_SUBJECT = "Your Conference Scheduler Sign-In Code"
_BODY_TEMPLATE = (
    "<p>Your one-time sign-in code is:</p>"
    "<h2 style='letter-spacing:4px'>{code}</h2>"
    "<p>This code expires in 10 minutes. Do not share it with anyone.</p>"
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
    """Shared SMTP dispatch. Logs in dev if SMTP credentials are not set."""
    settings = get_settings()
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("[DEV] Email to %s | %s", to_email, subject)
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_username
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def send_otp_email(to_email: str, otp_code: str) -> None:
    """Send the OTP to *to_email* via SMTP.

    If SMTP credentials are not configured, logs the code at WARNING level
    so local development works without email credentials.
    """
    _send(to_email, _SUBJECT, _BODY_TEMPLATE.format(code=otp_code))


def send_dept_head_notification(to_email: str, name: str, symposium_name: str, login_url: str) -> None:
    _send(to_email, _DEPT_HEAD_SUBJECT, _DEPT_HEAD_BODY.format(name=name, symposium_name=symposium_name, login_url=login_url))


def send_professor_notification(to_email: str, name: str, symposium_name: str, login_url: str) -> None:
    _send(to_email, _PROFESSOR_SUBJECT, _PROFESSOR_BODY.format(name=name, symposium_name=symposium_name, login_url=login_url))


def send_student_notification(to_email: str, name: str, symposium_name: str, login_url: str) -> None:
    _send(to_email, _STUDENT_SUBJECT, _STUDENT_BODY.format(name=name, symposium_name=symposium_name, login_url=login_url))
