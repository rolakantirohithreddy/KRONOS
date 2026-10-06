"""Tests for the KRONOS authentication endpoints."""

import logging
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.models.user import Base, get_db, User
from app.services.logger_service import LOGGER_NAME

# Use in-memory SQLite with StaticPool so the same connection is reused.
# This prevents the "no such table" error that occurs when SQLite in-memory
# databases create a new database per connection.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def disable_email_delivery(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_api_key", None)


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """Provide a test database session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """Provide a test client with database dependency overridden."""
    from app.main import app

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email="test@example.com", password="Password123"):
    """Helper: register a user and return the response."""
    return client.post("/auth/register", json={
        "email": email,
        "password": password,
        "confirm_password": password,
    })


def _get_otp(db, email="test@example.com") -> str:
    """Helper: retrieve the OTP from the test database."""
    user = db.query(User).filter(User.email == email).first()
    return user.otp_code


def _verify(client, db, email="test@example.com"):
    """Helper: verify a registered user via OTP."""
    otp = _get_otp(db, email)
    return client.post("/auth/verify-otp", json={
        "email": email,
        "otp_code": otp,
    })


def _login(client, email="test@example.com", password="Password123"):
    """Helper: attempt login and return the response."""
    return client.post("/auth/login", json={
        "email": email,
        "password": password,
    })


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_success(client, db):
    response = _register(client)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Registration successful. Please verify your email."
    assert data["email"] == "test@example.com"


def test_register_dev_mode_logs_otp(client, db):
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        response = _register(client)
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    otp = _get_otp(db)
    messages = [record.getMessage() for record in records]
    assert f"[DEV MODE - NO EMAIL SENT] OTP for test@example.com: {otp} (expires in 10 minutes)" in messages


def test_register_resend_403_restricted_domain_logs_otp(client, db, monkeypatch):
    import resend
    from resend.exceptions import ResendError

    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    monkeypatch.setattr(get_settings(), "resend_from_email", "onboarding@resend.dev")

    def mock_send(payload):
        raise ResendError(
            code=403,
            error_type="validation_error",
            message="You can only send testing emails to your own email address (owner@example.com). To send to other domains, you need to verify a domain at resend.com/domains.",
            suggested_action="",
        )

    monkeypatch.setattr(resend.Emails, "send", mock_send)

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        response = _register(client, email="newuser@example.com")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    assert response.json()["message"] == "Registration successful. Please verify your email."
    otp = _get_otp(db, email="newuser@example.com")
    messages = [record.getMessage() for record in records]
    expected_log = (
        f"[DEV MODE - EMAIL RESTRICTED] Resend can't deliver to newuser@example.com on the free testing domain. "
        f"OTP for newuser@example.com: {otp} (expires in 10 minutes)"
    )
    assert expected_log in messages


def test_register_resend_other_error_falls_back_to_console_otp(client, db, monkeypatch):
    import resend

    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test_key")
    monkeypatch.setattr(get_settings(), "resend_from_email", "security@example.com")

    def mock_send(payload):
        raise RuntimeError("Network connection error")

    monkeypatch.setattr(resend.Emails, "send", mock_send)

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        response = _register(client, email="fallback@example.com")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    assert response.json()["message"] == "Registration successful. Please verify your email."
    otp = _get_otp(db, email="fallback@example.com")
    messages = [record.getMessage() for record in records]
    expected_log = f"[DEV MODE - NO EMAIL SENT] OTP for fallback@example.com: {otp} (expires in 10 minutes)"
    assert expected_log in messages


def test_register_unverified_email_can_retry(client, db):
    _register(client)
    response = _register(client)
    assert response.status_code == 200
    assert response.json()["message"] == "Registration successful. Please verify your email."


def test_register_password_mismatch(client, db):
    response = client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "Password123",
        "confirm_password": "DifferentPassword",
    })
    assert response.status_code == 400
    assert "do not match" in response.json()["detail"].lower()


# ── OTP Verification ─────────────────────────────────────────────────────────

def test_verify_otp_success(client, db):
    _register(client)
    response = _verify(client, db)
    assert response.status_code == 200
    assert response.json()["message"] == "Email verified successfully."


def test_verify_wrong_otp(client, db):
    _register(client)
    response = client.post("/auth/verify-otp", json={
        "email": "test@example.com",
        "otp_code": "000000",
    })
    assert response.status_code == 400
    assert "Invalid or expired OTP" in response.json()["detail"]


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_before_verification(client, db):
    _register(client)
    response = _login(client)
    assert response.status_code == 403
    assert response.json()["detail"] == "Please verify your email."


def test_full_register_verify_login_flow(client, db):
    _register(client)
    _verify(client, db)
    response = _login(client)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_login_wrong_password(client, db):
    """Wrong password returns a generic 'Invalid credentials' message
    (security best practice: don't reveal whether the email exists)."""
    _register(client)
    _verify(client, db)
    response = _login(client, password="WrongPassword")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials."


def test_login_nonexistent_email(client, db):
    """Non-existent email also returns the same generic message."""
    response = _login(client, email="nobody@example.com")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials."


# ── Forgot / Reset Password ──────────────────────────────────────────────────

def test_forgot_reset_password_flow(client, db):
    _register(client)
    _verify(client, db)

    # Request password reset
    response = client.post("/auth/forgot-password", json={
        "email": "test@example.com",
    })
    assert response.status_code == 200

    # Retrieve the new OTP
    otp = _get_otp(db)

    # Reset the password
    response = client.post("/auth/reset-password", json={
        "email": "test@example.com",
        "otp_code": otp,
        "new_password": "NewPassword456",
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Password reset successful."

    # Login with the new password
    response = _login(client, password="NewPassword456")
    assert response.status_code == 200
    assert "access_token" in response.json()


# ── /auth/me ──────────────────────────────────────────────────────────────────

def test_me_endpoint_with_valid_token(client, db):
    _register(client)
    _verify(client, db)
    login_response = _login(client)
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "test@example.com"
    assert payload["is_verified"] is True


def test_me_endpoint_without_token(client, db):
    response = client.get("/auth/me")
    assert response.status_code == 401
