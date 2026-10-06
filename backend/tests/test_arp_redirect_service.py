"""Unit tests for app.services.arp_redirect_service."""

from unittest.mock import patch, MagicMock
import pytest

from app.services import arp_redirect_service


def test_get_route_for_target_success_unpacks_correctly():
    """Verify Scapy's (iface, output_ip, gateway_ip) tuple is correctly unpacked."""
    mock_target_route = ("eth0", "192.168.1.50", "0.0.0.0")
    mock_default_route = ("eth0", "192.168.1.50", "192.168.1.1")

    with patch("scapy.all.conf.route.route") as mock_route:
        def side_effect(dst, dev=None):
            if dst == "192.168.1.100":
                return mock_target_route
            if dst == "0.0.0.0":
                return mock_default_route
            return None

        mock_route.side_effect = side_effect

        gw, iface, own_ip = arp_redirect_service._get_route_for_target("192.168.1.100")
        assert gw == "192.168.1.1"
        assert iface == "eth0"
        assert own_ip == "192.168.1.50"


def test_get_route_for_target_fails_when_no_gateway():
    """Verify RuntimeError is raised if default gateway cannot be resolved."""
    mock_target_route = ("eth0", "192.168.1.50", "0.0.0.0")
    mock_default_route = ("eth0", "192.168.1.50", "0.0.0.0")

    with patch("scapy.all.conf.route.route") as mock_route, \
         patch("scapy.all.conf.route.routes", []):
        def side_effect(dst, dev=None):
            if dst == "192.168.1.100":
                return mock_target_route
            if dst == "0.0.0.0":
                return mock_default_route
            return None

        mock_route.side_effect = side_effect

        with pytest.raises(RuntimeError) as exc_info:
            arp_redirect_service._get_route_for_target("192.168.1.100")
        assert "Could not determine a valid default gateway" in str(exc_info.value)


def test_start_redirect_rejects_monitoring_own_ip():
    """Targeting own IP should raise informative error."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            arp_redirect_service.start_redirect("192.168.1.50")
        assert "Target IP (192.168.1.50) is this machine's own IP address" in str(exc_info.value)


def test_start_redirect_rejects_monitoring_gateway_itself():
    """Targeting the gateway router itself should raise informative error when not a camera."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ), patch(
        "app.services.discovery_service.fingerprint_device",
        return_value={"device_type": "unknown", "confidence": "low", "details": "Unknown"},
    ):
        with pytest.raises(RuntimeError) as exc_info:
            arp_redirect_service.start_redirect("192.168.1.1")
        assert "Target IP (192.168.1.1) is your LAN gateway / router" in str(exc_info.value)


def test_start_redirect_allows_fingerprinted_hotspot_camera_when_gateway():
    """When target IP matches the gateway but is fingerprinted as an IP camera, start_redirect succeeds."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("10.17.144.193", "Wi-Fi", "10.17.144.224"),
    ), patch(
        "app.services.discovery_service.fingerprint_device",
        return_value={"device_type": "ip_camera_phone", "confidence": "high", "details": "Android IP Webcam"},
    ), patch.object(
        arp_redirect_service,
        "_resolve_mac",
        side_effect=["aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"],
    ), patch("threading.Thread") as mock_thread_cls:

        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        res = arp_redirect_service.start_redirect("10.17.144.193")
        assert res["status"] == "started"
        assert res["target_ip"] == "10.17.144.193"
        assert res["gateway_ip"] == "10.17.144.193"

        info = arp_redirect_service.get_redirect_info("10.17.144.193")
        assert info is not None
        assert info["we_enabled_forwarding"] is False

        stop_res = arp_redirect_service.stop_redirect("10.17.144.193")
        assert stop_res["status"] == "stopped"


def test_start_redirect_mac_resolution_failure():
    """When MAC resolution fails, raise RuntimeError with detail."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ), patch.object(
        arp_redirect_service,
        "_resolve_mac",
        side_effect=[None, "aa:bb:cc:dd:ee:ff"],
    ):
        with pytest.raises(RuntimeError) as exc_info:
            arp_redirect_service.start_redirect("192.168.1.100")
        assert "Could not resolve MAC address for target (None (unreachable))" in str(exc_info.value)


def test_start_redirect_success_and_stop():
    """Valid target and gateway resolve MACs, enable IP forwarding, and start/stop cleanly."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ), patch.object(
        arp_redirect_service,
        "_resolve_mac",
        side_effect=["11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff"],
    ), patch.object(
        arp_redirect_service,
        "_set_ip_forwarding",
        return_value=True,
    ), patch("threading.Thread") as mock_thread_cls, \
       patch("app.services.arp_redirect_service.sendp"):

        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        res = arp_redirect_service.start_redirect("192.168.1.100")
        assert res["status"] == "started"
        assert res["target_ip"] == "192.168.1.100"
        assert res["gateway_ip"] == "192.168.1.1"

        status = arp_redirect_service.get_status()
        assert "192.168.1.100" in status["active_targets"]
        assert status["count"] == 1

        stop_res = arp_redirect_service.stop_redirect("192.168.1.100")
        assert stop_res["status"] == "stopped"

        status_after = arp_redirect_service.get_status()
        assert status_after["count"] == 0


def test_is_gateway_returns_true_when_ip_matches():
    """is_gateway returns True when target IP matches the resolved gateway."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ):
        assert arp_redirect_service.is_gateway("192.168.1.1") is True


def test_is_gateway_returns_false_when_ip_differs():
    """is_gateway returns False when target IP does not match the resolved gateway."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ):
        assert arp_redirect_service.is_gateway("192.168.1.100") is False


def test_is_gateway_returns_false_on_exception_or_own_ip():
    """is_gateway returns False safely when _get_route_for_target raises (e.g. own IP)."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        side_effect=RuntimeError("Target IP is this host machine itself"),
    ):
        assert arp_redirect_service.is_gateway("192.168.1.50") is False


def test_get_active_network_success():
    """get_active_network returns (iface, own_ip, gateway_ip) from route resolution."""
    with patch.object(
        arp_redirect_service,
        "_get_route_for_target",
        return_value=("192.168.1.1", "eth0", "192.168.1.50"),
    ):
        iface, own_ip, gw_ip = arp_redirect_service.get_active_network()
        assert iface == "eth0"
        assert own_ip == "192.168.1.50"
        assert gw_ip == "192.168.1.1"
