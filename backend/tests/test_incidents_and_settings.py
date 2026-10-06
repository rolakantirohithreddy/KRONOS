"""
Tests for GET /incidents, GET /incidents/stats, and POST /auth/change-password.
Uses an in-memory SQLite DB to keep tests fully isolated from the real DB.
"""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.user import Base, IncidentRecord, User, get_db
from app.services.auth_service import create_access_token, get_password_hash

# ── Shared in-memory DB ────────────────────────────────────────────────────────

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
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


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_incident(db, source: str, risk_label: str = "Low", latency: float = 123.0, idx: int = 0):
    """Insert a minimal IncidentRecord into the test DB."""
    r = IncidentRecord(
        request_id=f"req-{source}-{idx}",
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        attack_type="DDoS" if risk_label != "Low" else "Benign",
        confidence=0.95,
        risk_label=risk_label,
        risk_score=0.8 if risk_label in ("High", "Critical") else 0.1,
        source=source,
        pipeline_latency_ms=latency,
        evidence_summary="High SYN flag ratio observed.",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_user(db, email="u@example.com", password="Password123"):
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(email="u@example.com"):
    token = create_access_token({"sub": email})
    return {"Authorization": f"Bearer {token}"}


# ══ GET /incidents ════════════════════════════════════════════════════════════


def test_incidents_empty_returns_list(client, db):
    res = client.get("/incidents")
    assert res.status_code == 200
    assert res.json() == []


def test_incidents_returns_all(client, db):
    _make_incident(db, "live", idx=0)
    _make_incident(db, "test", idx=1)
    _make_incident(db, "manual_simulate", idx=2)
    res = client.get("/incidents")
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_incidents_filter_by_source_live(client, db):
    _make_incident(db, "live", idx=0)
    _make_incident(db, "test", idx=1)
    res = client.get("/incidents", params={"source": "live"})
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["source"] == "live"


def test_incidents_filter_by_source_test(client, db):
    _make_incident(db, "live", idx=0)
    _make_incident(db, "test", idx=1)
    _make_incident(db, "test", idx=2)
    res = client.get("/incidents", params={"source": "test"})
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all(d["source"] == "test" for d in data)


def test_incidents_limit(client, db):
    for i in range(10):
        _make_incident(db, "test", idx=i)
    res = client.get("/incidents", params={"limit": 3})
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_incidents_newest_first(client, db):
    import time
    r1 = _make_incident(db, "live", idx=0)
    time.sleep(0.01)
    r2 = _make_incident(db, "live", idx=1)
    res = client.get("/incidents", params={"source": "live"})
    data = res.json()
    assert data[0]["id"] == r2.id  # newest first
    assert data[1]["id"] == r1.id


def test_incidents_response_fields(client, db):
    _make_incident(db, "live", risk_label="High", idx=0)
    res = client.get("/incidents")
    data = res.json()
    item = data[0]
    for field in ("id", "request_id", "timestamp", "attack_type", "risk_label", "confidence", "source", "mitigated", "pipeline_latency_ms"):
        assert field in item, f"Missing field: {field}"


# ══ GET /incidents/stats ═════════════════════════════════════════════════════


def test_incidents_stats_empty(client, db):
    res = client.get("/incidents/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_incidents"] == 0
    assert data["high_critical_count"] == 0
    assert data["avg_pipeline_latency_ms"] == 0.0


def test_incidents_stats_counts(client, db):
    _make_incident(db, "live", risk_label="High", latency=100.0, idx=0)
    _make_incident(db, "live", risk_label="Critical", latency=200.0, idx=1)
    _make_incident(db, "test", risk_label="Low", latency=300.0, idx=2)

    res = client.get("/incidents/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_incidents"] == 3
    assert data["high_critical_count"] == 2
    assert abs(data["avg_pipeline_latency_ms"] - 200.0) < 0.1  # (100+200+300)/3


# ══ POST /auth/change-password ════════════════════════════════════════════════


def test_change_password_success(client, db):
    _make_user(db)
    headers = _auth_headers()
    res = client.post(
        "/auth/change-password",
        json={"current_password": "Password123", "new_password": "NewPass456!", "confirm_password": "NewPass456!"},
        headers=headers,
    )
    assert res.status_code == 200
    assert "Password updated successfully" in res.json()["message"]

    # Can log in with the new password
    login = client.post("/auth/login", json={"email": "u@example.com", "password": "NewPass456!"})
    assert login.status_code == 200


def test_change_password_wrong_current(client, db):
    _make_user(db)
    headers = _auth_headers()
    res = client.post(
        "/auth/change-password",
        json={"current_password": "WRONGPASSWORD", "new_password": "NewPass456!", "confirm_password": "NewPass456!"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "Current password is incorrect" in res.json()["detail"]


def test_change_password_mismatch(client, db):
    _make_user(db)
    headers = _auth_headers()
    res = client.post(
        "/auth/change-password",
        json={"current_password": "Password123", "new_password": "NewPass456!", "confirm_password": "DifferentPass!"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "do not match" in res.json()["detail"]


def test_change_password_too_short(client, db):
    _make_user(db)
    headers = _auth_headers()
    res = client.post(
        "/auth/change-password",
        json={"current_password": "Password123", "new_password": "short", "confirm_password": "short"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "8 characters" in res.json()["detail"]


def test_change_password_requires_auth(client, db):
    res = client.post(
        "/auth/change-password",
        json={"current_password": "x", "new_password": "NewPass456!", "confirm_password": "NewPass456!"},
    )
    assert res.status_code == 401
