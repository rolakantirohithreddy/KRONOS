import logging

import pytest

from app.config import get_settings
from app.services import email_service
from app.services.email_service import EmailDeliveryError
from app.services.logger_service import LOGGER_NAME


def test_send_otp_email_dev_mode_logs_otp(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", None)
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)

    try:
        email_service.send_otp_email("dev@example.com", "123456", "email")
    finally:
        logger.removeHandler(handler)

    messages = [record.getMessage() for record in records]
    assert "[DEV MODE - NO EMAIL SENT] OTP for dev@example.com: 123456 (expires in 10 minutes)" in messages


def test_send_otp_email_calls_resend(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    monkeypatch.setattr(get_settings(), "resend_from_email", "security@example.com")
    calls = []
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: calls.append(payload))

    email_service.send_otp_email("user@example.com", "654321", "email")

    assert calls[0]["from"] == "security@example.com"
    assert calls[0]["to"] == "user@example.com"
    assert "654321" in calls[0]["html"]


def test_send_otp_email_requires_configured_sender(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    monkeypatch.setattr(get_settings(), "resend_from_email", None)

    with pytest.raises(EmailDeliveryError, match="KRONOS_RESEND_FROM_EMAIL"):
        email_service.send_otp_email("user@example.com", "654321", "email")


def test_send_otp_email_logs_resend_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    monkeypatch.setattr(get_settings(), "resend_from_email", "security@example.com")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    monkeypatch.setattr(
        email_service.resend.Emails,
        "send",
        lambda payload: (_ for _ in ()).throw(RuntimeError("sender domain not verified")),
    )

    try:
        email_service.send_otp_email("user@example.com", "654321", "email")
    finally:
        logger.removeHandler(handler)

    messages = [record.getMessage() for record in records]
    assert any("sender domain not verified" in m for m in messages)
    assert "[DEV MODE - NO EMAIL SENT] OTP for user@example.com: 654321 (expires in 10 minutes)" in messages


def test_send_otp_email_403_restricted_domain_logs_otp(monkeypatch):
    from resend.exceptions import ResendError

    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    monkeypatch.setattr(get_settings(), "resend_from_email", "onboarding@resend.dev")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    monkeypatch.setattr(
        email_service.resend.Emails,
        "send",
        lambda payload: (_ for _ in ()).throw(
            ResendError(
                code=403,
                error_type="validation_error",
                message="You can only send testing emails to your own email address (owner@example.com).",
                suggested_action="",
            )
        ),
    )

    try:
        email_service.send_otp_email("other@example.com", "789012", "email")
    finally:
        logger.removeHandler(handler)

    messages = [r.getMessage() for r in records]
    assert (
        "[DEV MODE - EMAIL RESTRICTED] Resend can't deliver to other@example.com on the free testing domain. "
        "OTP for other@example.com: 789012 (expires in 10 minutes)"
    ) in messages