"""app/services/discovery_service.py

Live network device discovery and IoT / IP camera fingerprinting.
Discovers real devices connected to the local network and automatically
identifies phone-based or generic IoT cameras without manual entry.
Never uses mock or hardcoded placeholder data.
"""

import concurrent.futures
import logging
import re
import socket
import subprocess
import urllib.request
from typing import Any

from scapy.all import conf, getmacbyip

from app.services.arp_redirect_service import (
    is_gateway,
    get_active_network,
    _resolve_mac,
    resync_network_state,
)

log = logging.getLogger("kronos.discovery")


def fingerprint_device(ip: str) -> dict[str, Any]:
    """
    Lightweight fingerprint check to recognize phone-based or generic IoT cameras.

    Checks:
    1. HTTP GET to http://<ip>:8080/ with ~1.5s timeout.
       Checks Server header and HTML body/title for Android "IP Webcam" signatures.
       If matched -> device_type="ip_camera_phone", confidence="high"
    2. TCP port 554 (RTSP) for generic IP camera video streaming.
       If open -> device_type="ip_camera", confidence="medium"
    3. HTTP GET to http://<ip>:80/ for camera web interfaces.
       If camera signatures found -> device_type="ip_camera", confidence="medium"
    4. Otherwise -> device_type="unknown", confidence="low"

    Returns:
        dict: {device_type: str, confidence: str, details: str}
    """
    # 1. Primary check: Android "IP Webcam" app on port 8080
    try:
        req = urllib.request.Request(
            f"http://{ip}:8080/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KRONOS-Scanner/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            headers = dict(resp.headers)
            server_header = headers.get("Server", "")
            raw_body = resp.read(4096).decode("utf-8", errors="ignore")

            is_server_match = "ip webcam" in server_header.lower()
            is_body_match = (
                "ip webcam" in raw_body.lower()
                or "<title>ip webcam" in raw_body.lower()
                or 'content="ip webcam"' in raw_body.lower()
            )

            if is_server_match or is_body_match:
                server_desc = f" ({server_header.strip()})" if server_header else ""
                log.info(f"Fingerprinted {ip} as Android IP Webcam on port 8080{server_desc}")
                return {
                    "device_type": "ip_camera_phone",
                    "confidence": "high",
                    "details": f"Android IP Webcam detected on port 8080{server_desc}",
                }
    except Exception:
        pass

    # 2. Check port 554 (RTSP standard port for IoT security / streaming cameras)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        res = sock.connect_ex((ip, 554))
        sock.close()
        if res == 0:
            log.info(f"Fingerprinted {ip} as generic IP camera (RTSP port 554 open)")
            return {
                "device_type": "ip_camera",
                "confidence": "medium",
                "details": "RTSP streaming service active on port 554",
            }
    except Exception:
        pass

    # 3. Fallback generic camera check on port 80 (HTTP)
    try:
        req = urllib.request.Request(
            f"http://{ip}:80/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KRONOS-Scanner/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            headers = dict(resp.headers)
            server_header = headers.get("Server", "").lower()
            raw_body = resp.read(4096).decode("utf-8", errors="ignore").lower()
            camera_keywords = ["camera", "webcam", "ipcam", "netcam", "dvr", "nvr", "surveillance"]

            if any(kw in server_header for kw in camera_keywords) or any(kw in raw_body for kw in camera_keywords):
                log.info(f"Fingerprinted {ip} as generic camera web interface on port 80")
                return {
                    "device_type": "ip_camera",
                    "confidence": "medium",
                    "details": "Camera web interface detected on port 80",
                }
    except Exception:
        pass

    return {
        "device_type": "unknown",
        "confidence": "low",
        "details": "Standard network endpoint",
    }


def _get_active_network() -> tuple[str | None, str, str | None]:
    """Return (interface_name, own_ip, default_gateway_ip) using unified interface-specific route resolution."""
    return get_active_network()


def _parse_arp_table(own_ip: str, subnet_prefix: str) -> dict[str, str]:
    """Parse system ARP cache for IP-MAC mappings on the active subnet."""
    arp_entries: dict[str, str] = {}
    try:
        out = subprocess.check_output(["arp", "-a"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            m = re.match(r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s+([0-9a-fA-F-]+)\s+(\w+)", line.strip())
            if m:
                ip = m.group(1)
                mac = m.group(2).replace("-", ":").lower()
                if (
                    ip.startswith(subnet_prefix)
                    and ip != own_ip
                    and not ip.endswith(".255")
                    and not ip.startswith("224.")
                    and not ip.startswith("239.")
                    and mac != "ff:ff:ff:ff:ff:ff"
                ):
                    arp_entries[ip] = mac
    except Exception as e:
        log.warning(f"Could not read ARP table via arp -a: {e}")
    return arp_entries


def _probe_host(ip: str) -> str | None:
    """Quick port check to awaken asleep LAN devices and populate OS ARP tables."""
    for port in (8080, 80, 554, 443):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.2)
        try:
            res = sock.connect_ex((ip, port))
            sock.close()
            if res == 0:
                return ip
        except Exception:
            pass
    return None


def discover_devices() -> list[dict[str, Any]]:
    """
    Live scan of the local LAN to discover active network devices and fingerprint them.
    Never returns mock/placeholder data under any circumstances.

    Returns:
        list of device dicts:
            [
                {
                    "id": str,
                    "ip": str,
                    "mac": str,
                    "name": str,
                    "device_type": "ip_camera_phone" | "ip_camera" | "unknown",
                    "confidence": "high" | "medium" | "low",
                    "is_gateway": bool,
                    "description": str,
                },
                ...
            ]
    """
    resync_network_state()
    iface, own_ip, gw_ip = _get_active_network()
    log.info(f"Starting real device discovery on iface '{iface}' (own IP: {own_ip}, gateway: {gw_ip})")

    candidates: dict[str, str | None] = {}

    # Always ensure the gateway is considered
    if gw_ip and gw_ip != "0.0.0.0" and gw_ip != own_ip:
        candidates[gw_ip] = None

    subnet_prefix = ""
    if own_ip and "." in own_ip and not own_ip.startswith("127."):
        subnet_prefix = own_ip.rsplit(".", 1)[0] + "."

        # Read known ARP entries
        arp_entries = _parse_arp_table(own_ip, subnet_prefix)
        for ip, mac in arp_entries.items():
            candidates[ip] = mac

        # Fast sweep across the /24 subnet to awaken any quiet devices
        sweep_ips = [
            f"{subnet_prefix}{i}"
            for i in range(1, 255)
            if f"{subnet_prefix}{i}" != own_ip and f"{subnet_prefix}{i}" not in candidates
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            active_ips = list(filter(None, executor.map(_probe_host, sweep_ips)))

        for ip in active_ips:
            if ip not in candidates:
                candidates[ip] = None

    # Resolve MACs and fingerprint each discovered candidate
    discovered_list: list[dict[str, Any]] = []

    for ip, known_mac in candidates.items():
        mac = known_mac
        if not mac or mac == "Unresolved":
            try:
                mac = _resolve_mac(ip, iface, timeout=1.5, retries=2) if iface else None
                if not mac:
                    mac = getmacbyip(ip)
            except Exception:
                mac = None

        fp = fingerprint_device(ip)
        is_gw_device = is_gateway(ip)
        # If the device is an IoT camera or phone webcam, it is an endpoint under test, not an infrastructure gateway
        if fp["device_type"] in ("ip_camera_phone", "ip_camera"):
            is_gw = False
        else:
            is_gw = is_gw_device

        # Name heuristic
        if fp["device_type"] == "ip_camera_phone":
            name = "Android IP Webcam (Phone)"
        elif fp["device_type"] == "ip_camera":
            name = "IoT Camera"
        elif is_gw:
            name = "LAN Gateway / Router"
        else:
            name = f"Network Device ({ip})"

        discovered_list.append({
            "id": f"dev-{ip.replace('.', '-')}",
            "ip": ip,
            "mac": mac or "Unresolved",
            "name": name,
            "device_type": fp["device_type"],
            "confidence": fp["confidence"],
            "is_gateway": is_gw,
            "description": fp["details"],
        })

    # Sort: Phone cameras first, other cameras next, then gateways and general endpoints
    type_priority = {
        "ip_camera_phone": 0,
        "ip_camera": 1,
        "unknown": 2,
    }
    discovered_list.sort(key=lambda d: (type_priority.get(d["device_type"], 3), d["ip"]))

    log.info(f"Device discovery complete: found {len(discovered_list)} devices.")
    return discovered_list
