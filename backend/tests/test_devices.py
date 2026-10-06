"""Tests for device discovery and IP camera fingerprinting."""

from unittest.mock import patch, MagicMock
from io import BytesIO
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import discovery_service

client = TestClient(app)


def test_fingerprint_device_ip_webcam_phone():
    """Verify a device responding with 'IP Webcam' gets device_type='ip_camera_phone'."""
    mock_response = MagicMock()
    mock_response.headers = {"Server": "IP Webcam Server 0.4"}
    mock_response.read.return_value = b"<html><head><title>IP Webcam</title></head></html>"
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = discovery_service.fingerprint_device("192.168.1.50")
        assert result["device_type"] == "ip_camera_phone"
        assert result["confidence"] == "high"
        assert "IP Webcam" in result["details"]


def test_fingerprint_device_unknown_when_no_response():
    """Verify an unreachable host or standard device gets device_type='unknown'."""
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")), \
         patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # Connection refused
        mock_sock_cls.return_value = mock_sock

        result = discovery_service.fingerprint_device("192.168.1.99")
        assert result["device_type"] == "unknown"
        assert result["confidence"] == "low"


def test_fingerprint_device_rtsp_camera():
    """Verify open RTSP port 554 identifies as generic IoT camera."""
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")), \
         patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0  # Port open
        mock_sock_cls.return_value = mock_sock

        result = discovery_service.fingerprint_device("192.168.1.120")
        assert result["device_type"] == "ip_camera"
        assert result["confidence"] == "medium"
        assert "554" in result["details"]


def test_discover_devices_real_structure():
    """Verify discover_devices properly labels gateway and fingerprinted devices."""
    mock_network = ("eth0", "192.168.1.20", "192.168.1.1")
    mock_arp = {"192.168.1.1": "00:11:22:33:44:55", "192.168.1.60": "aa:bb:cc:dd:ee:ff"}

    def mock_fp(ip):
        if ip == "192.168.1.60":
            return {"device_type": "ip_camera_phone", "confidence": "high", "details": "Android IP Webcam"}
        return {"device_type": "unknown", "confidence": "low", "details": "Standard network endpoint"}

    with patch("app.services.discovery_service._get_active_network", return_value=mock_network), \
         patch("app.services.discovery_service._parse_arp_table", return_value=mock_arp), \
         patch("app.services.discovery_service.fingerprint_device", side_effect=mock_fp), \
         patch("app.services.discovery_service.is_gateway", side_effect=lambda ip: ip == "192.168.1.1"), \
         patch("app.services.discovery_service._probe_host", return_value=None):

        devices = discovery_service.discover_devices()
        assert len(devices) == 2

        phone_cam = next(d for d in devices if d["ip"] == "192.168.1.60")
        assert phone_cam["device_type"] == "ip_camera_phone"
        assert phone_cam["confidence"] == "high"
        assert phone_cam["is_gateway"] is False
        assert "IP Webcam" in phone_cam["name"]

        gw_dev = next(d for d in devices if d["ip"] == "192.168.1.1")
        assert gw_dev["is_gateway"] is True
        assert gw_dev["mac"] == "00:11:22:33:44:55"


def test_get_devices_endpoint_never_returns_old_hardcoded_placeholders():
    """Verify GET /devices never returns old mock placeholder cards (192.168.1.105, dev-1, etc.)."""
    response = client.get("/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    # Assert none of the old mock card IPs or names appear
    old_mock_ips = {"192.168.1.105", "192.168.1.145", "192.168.1.112"}
    old_mock_names = {"IoT Webcam (Demo Node)", "Mobile Client (Test Controller)", "Smart Gateway / Hub"}
    old_mock_ids = {"dev-1", "dev-2", "dev-3"}

    for dev in data:
        assert dev["ip"] not in old_mock_ips, f"Found old mock IP: {dev['ip']}"
        assert dev["name"] not in old_mock_names, f"Found old mock name: {dev['name']}"
        assert dev["id"] not in old_mock_ids, f"Found old mock ID: {dev['id']}"
