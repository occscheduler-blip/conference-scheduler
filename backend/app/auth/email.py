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
