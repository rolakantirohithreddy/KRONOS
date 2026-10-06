"""Tests for the KRONOS health endpoint."""

from datetime import datetime

from starlette.testclient import TestClient

from app.main import app


def test_health_returns_expected_shape() -> None:
    """Verify health reports status, an ISO timestamp, and the app version."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "timestamp", "version"}
    assert payload["status"] == "ok"
    assert datetime.fromisoformat(payload["timestamp"])
    assert payload["version"] == "0.1.0"