"""Tests for the /monitoring router endpoints."""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.routers.monitoring as monitoring_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_monitoring_state():
    """Reset module-level monitoring state before and after each test."""
    with monitoring_module._state_lock:
        monitoring_module._current_target_ip = None
        monitoring_module._last_cycle_at = None
        monitoring_module._packets_last_window = 0
    # Stop any capture thread that may be running
    if monitoring_module._capture_stop_event:
        monitoring_module._capture_stop_event.set()
    if monitoring_module._capture_thread:
        monitoring_module._capture_thread.join(timeout=2)
    monitoring_module._capture_stop_event = None
    monitoring_module._capture_thread = None
    monitoring_module._log_buffer.clear()
    yield
    with monitoring_module._state_lock:
        monitoring_module._current_target_ip = None
        monitoring_module._last_cycle_at = None
        monitoring_module._packets_last_window = 0
    if monitoring_module._capture_stop_event:
        monitoring_module._capture_stop_event.set()
    if monitoring_module._capture_thread:
        monitoring_module._capture_thread.join(timeout=2)
    monitoring_module._capture_stop_event = None
    monitoring_module._capture_thread = None


def test_monitoring_status_initially_inactive():
    with patch("app.services.arp_redirect_service.get_status", return_value={"active_targets": [], "count": 0}):
        response = client.get("/monitoring/status")
        assert response.status_code == 200
        data = response.json()
        assert data["monitoring_active"] is False
        assert data["current_target_ip"] is None
        assert data["arp_redirect"]["count"] == 0
        assert data["capture_loop_alive"] is False
        assert data["packets_seen_last_window"] == 0


def test_monitoring_start_success():
    mock_redirect = {
        "status": "started",
        "target_ip": "192.168.1.105",
        "gateway_ip": "192.168.1.1",
    }
    with patch("app.services.arp_redirect_service.start_redirect", return_value=mock_redirect) as mock_start, \
         patch("app.routers.monitoring._capture_loop"):  # prevent real capture loop
        response = client.post("/monitoring/start", json={"target_ip": "192.168.1.105"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "monitoring_started"
        assert data["target_ip"] == "192.168.1.105"
        assert data["redirect"] == mock_redirect
        mock_start.assert_called_once_with(target_ip="192.168.1.105", gateway_ip=None)


def test_monitoring_start_failure_returns_422():
    with patch(
        "app.services.arp_redirect_service.start_redirect",
        side_effect=RuntimeError("Could not resolve MAC address for target (None). Confirm device is online."),
    ):
        response = client.post("/monitoring/start", json={"target_ip": "192.168.1.200"})
        assert response.status_code == 422
        assert "Could not resolve MAC address" in response.json()["detail"]


def test_monitoring_start_conflict_when_already_monitoring():
    mock_redirect = {"status": "started", "target_ip": "192.168.1.10", "gateway_ip": "192.168.1.1"}
    with patch("app.services.arp_redirect_service.start_redirect", return_value=mock_redirect), \
         patch("app.routers.monitoring._capture_loop"):
        res1 = client.post("/monitoring/start", json={"target_ip": "192.168.1.10"})
        assert res1.status_code == 200

        res2 = client.post("/monitoring/start", json={"target_ip": "192.168.1.20"})
        assert res2.status_code == 409
        assert "Already monitoring 192.168.1.10" in res2.json()["detail"]


def test_monitoring_stop_success():
    mock_redirect_start = {"status": "started", "target_ip": "192.168.1.55", "gateway_ip": "192.168.1.1"}
    mock_redirect_stop = {"status": "stopped", "target_ip": "192.168.1.55"}

    with patch("app.services.arp_redirect_service.start_redirect", return_value=mock_redirect_start), \
         patch("app.routers.monitoring._capture_loop"):
        client.post("/monitoring/start", json={"target_ip": "192.168.1.55"})

    with patch("app.services.arp_redirect_service.stop_redirect", return_value=mock_redirect_stop) as mock_stop:
        response = client.post("/monitoring/stop", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "monitoring_stopped"
        assert data["target_ip"] == "192.168.1.55"
        mock_stop.assert_called_once_with("192.168.1.55")

    # Status should now be inactive
    with patch("app.services.arp_redirect_service.get_status", return_value={"active_targets": [], "count": 0}):
        status_res = client.get("/monitoring/status")
        assert status_res.json()["monitoring_active"] is False


def test_monitoring_stop_when_not_monitoring_returns_404():
    response = client.post("/monitoring/stop", json={})
    assert response.status_code == 404
    assert "No device is currently being monitored" in response.json()["detail"]


def test_monitoring_logs_returns_list():
    """GET /monitoring/logs should return the in-memory log buffer."""
    response = client.get("/monitoring/logs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_monitoring_status_includes_capture_fields():
    """GET /monitoring/status should include the new capture loop health fields."""
    with patch("app.services.arp_redirect_service.get_status", return_value={"active_targets": [], "count": 0}):
        response = client.get("/monitoring/status")
        assert response.status_code == 200
        data = response.json()
        assert "arp_redirect_active" in data
        assert "capture_loop_alive" in data
        assert "last_cycle_at" in data
        assert "packets_seen_last_window" in data
