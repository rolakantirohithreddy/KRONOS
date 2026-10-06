import logging
from typing import Any

import resend
from app.config import get_settings
from app.services.logger_service import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


class EmailDeliveryError(RuntimeError):
    """Raised when the Resend API cannot accept an email."""


def is_resend_403_restricted(exc: Any) -> bool:
    """Check if the exception represents Resend's 403 error for testing domain restrictions.

    When sending from onboarding@resend.dev to an address other than the account owner's,
    Resend returns a 403 Forbidden with a message like:
    'You can only send testing emails to your own email address (...). To send to other domains,
    you need to verify a domain at resend.com/domains.'
    """
    # 1. Check HTTP status code on ResendError or generic HTTP exception
    code = getattr(exc, "code", None)
    if code is None and hasattr(exc, "status_code"):
        code = getattr(exc, "status_code")
    if code is None and hasattr(exc, "response"):
        code = getattr(getattr(exc, "response"), "status_code", None)

    code_is_403 = str(code) == "403" or code == 403

    # 2. Check for restriction message indicators
    msg = str(exc).lower()
    restricted_phrases = (
        "can only send testing emails to your own email address",
        "only send testing emails",
        "your own email address",
        "testing domain",
        "free testing domain",
        "resend.com/domains",
    )
    has_restricted_msg = any(phrase in msg for phrase in restricted_phrases)

    if code_is_403:
        # Avoid treating invalid API key as domain restriction
        if getattr(exc, "error_type", None) == "invalid_api_key":
            return False
        return True

    return has_restricted_msg


def send_otp_email(recipient: str, otp: str, purpose: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning(
            "[DEV MODE - NO EMAIL SENT] OTP for %s: %s (expires in 10 minutes)",
            recipient,
            otp,
        )
        return
    if not settings.resend_from_email:
        raise EmailDeliveryError(
            "Set KRONOS_RESEND_FROM_EMAIL to an address on a verified Resend domain."
        )

    try:
        resend.api_key = settings.resend_api_key
        resend.Emails.send(
            {
                "from": settings.resend_from_email,
                "to": recipient,
                "subject": "Your OTP Code",
                "html": f"<h2>Your OTP is: {otp}</h2><p>This code expires in 10 minutes.</p>",
            }
        )
    except Exception as exc:
        if is_resend_403_restricted(exc):
            logger.warning(
                "[DEV MODE - EMAIL RESTRICTED] Resend can't deliver to %s on the free testing domain. "
                "OTP for %s: %s (expires in 10 minutes)",
                recipient,
                recipient,
                otp,
            )
            return

        logger.error(
            "Failed to send %s OTP email to %s via Resend: %s",
            purpose,
            recipient,
            exc,
            exc_info=True,
        )
        logger.warning(
            "[DEV MODE - NO EMAIL SENT] OTP for %s: %s (expires in 10 minutes)",
            recipient,
            otp,
        )
        return


def send_critical_alert_email(
    recipient: str,
    attack_type: str,
    source_ip: str | None,
    timestamp: str,
    dashboard_url: str = "http://localhost:5173/dashboard",
) -> None:
    """Send a critical-incident notification via Resend. No-op in dev mode (no API key)."""
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning(
            "[DEV MODE - NO EMAIL SENT] Critical alert for %s -> %s (%s)",
            recipient,
            attack_type,
            source_ip,
        )
        return
    if not settings.resend_from_email:
        logger.error("KRONOS_RESEND_FROM_EMAIL not set; cannot send critical alert.")
        return

    src = source_ip or "unknown"
    html = f"""
<h2 style="color:#dc2626">&#9888; KRONOS Critical Incident Detected</h2>
<table style="border-collapse:collapse;font-family:monospace">
  <tr><td style="padding:4px 12px 4px 0"><b>Attack Type</b></td><td>{attack_type}</td></tr>
  <tr><td style="padding:4px 12px 4px 0"><b>Source IP</b></td><td>{src}</td></tr>
  <tr><td style="padding:4px 12px 4px 0"><b>Timestamp</b></td><td>{timestamp}</td></tr>
</table>
<p><a href="{dashboard_url}">Open KRONOS Dashboard &rarr;</a></p>
"""
    try:
        resend.api_key = settings.resend_api_key
        resend.Emails.send(
            {
                "from": settings.resend_from_email,
                "to": recipient,
                "subject": f"[KRONOS] Critical Detection: {attack_type}",
                "html": html,
            }
        )
    except Exception as exc:
        if is_resend_403_restricted(exc):
            logger.warning(
                "[DEV MODE - EMAIL RESTRICTED] Resend can't deliver critical alert to %s on the free testing domain.",
                recipient,
            )
            return
        logger.error(
            "Failed to send critical alert email to %s: %s",
            recipient,
            exc,
            exc_info=True,
        )