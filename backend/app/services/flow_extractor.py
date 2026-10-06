"""
flow_extractor.py — Live packet capture, flow extraction, and ML inference.

Captures packets on the correct interface (from arp_redirect_service), groups
them into flows by 5-tuple, computes ALL 39 CIC-IoT-style features required
by the ML model, validates completeness, and runs inference.
"""

import json
import logging
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from scapy.all import sniff, IP, TCP, UDP, ICMP, ARP
from scapy.layers.l2 import LLC

# IGMP may not be available in all scapy versions
try:
    from scapy.contrib.igmp import IGMP
except ImportError:
    IGMP = None

from app.services import arp_redirect_service
from app.services.ml_model import inference

logger = logging.getLogger("kronos.flow_extractor")

# ── Load the authoritative feature list from feature_columns.json ────────────
_FEATURE_COLUMNS_PATH = (
    Path(__file__).resolve().parent / "ml_model" / "feature_columns.json"
)
with open(_FEATURE_COLUMNS_PATH, encoding="utf-8") as _f:
    FEATURE_COLUMNS: list[str] = json.load(_f)


def extract_flow_features(packets: list) -> dict[str, float]:
    """
    Extract ALL 39 CIC-IoT-style features from a list of packets forming a flow.

    Every feature key from FEATURE_COLUMNS is explicitly populated with a real
    computed value — no silent 0.0 defaults.
    """
    if not packets:
        return {}

    features: dict[str, float] = {}
    num_packets = len(packets)

    # ── Packet sizes ─────────────────────────────────────────────────────
    lengths = [float(len(pkt)) for pkt in packets]
    tot_sum = sum(lengths)

    features["Number"] = float(num_packets)
    features["Tot sum"] = tot_sum
    features["Tot size"] = tot_sum  # alias kept for model compatibility
    features["Min"] = min(lengths)
    features["Max"] = max(lengths)
    features["AVG"] = tot_sum / num_packets
    features["Std"] = float(statistics.stdev(lengths)) if num_packets >= 2 else 0.0
    features["Variance"] = float(statistics.variance(lengths)) if num_packets >= 2 else 0.0

    # ── Timing: IAT and Rate ─────────────────────────────────────────────
    timestamps = [float(getattr(pkt, "time", 0.0) or 0.0) for pkt in packets]
    if num_packets >= 2:
        iats = [timestamps[i] - timestamps[i - 1] for i in range(1, num_packets)]
        features["IAT"] = float(statistics.mean(iats))
        duration = timestamps[-1] - timestamps[0]
        features["Rate"] = float(num_packets / duration) if duration > 0 else float(num_packets)
    else:
        features["IAT"] = 0.0
        features["Rate"] = float(num_packets)

    # ── Header Length (cumulative IP header bytes) ────────────────────────
    header_length = 0.0
    for pkt in packets:
        if IP in pkt:
            ihl = pkt[IP].ihl if getattr(pkt[IP], "ihl", None) is not None else 5
            header_length += float(ihl * 4)
        else:
            header_length += 14.0  # Ethernet header fallback
    features["Header_Length"] = header_length

    # ── Protocol Type (IP proto number, last packet's value) ─────────────
    protocol_type = 0.0
    for pkt in packets:
        if IP in pkt and getattr(pkt[IP], "proto", None) is not None:
            protocol_type = float(pkt[IP].proto)
    features["Protocol Type"] = protocol_type

    # ── Time To Live (average across IP packets) ─────────────────────────
    ttls = [
        float(pkt[IP].ttl if getattr(pkt[IP], "ttl", None) is not None else 64)
        for pkt in packets
        if IP in pkt
    ]
    features["Time_To_Live"] = float(statistics.mean(ttls)) if ttls else 0.0

    # ── TCP flag presence indicators (binary: 1.0 if ANY packet has it) ──
    fin_flag = syn_flag = rst_flag = psh_flag = ack_flag = ece_flag = cwr_flag = False
    fin_count = syn_count = rst_count = ack_count = 0

    for pkt in packets:
        if TCP in pkt:
            raw_flags = getattr(pkt[TCP], "flags", 0)
            flags_str = str(raw_flags)
            try:
                flags_val = int(raw_flags)
            except (ValueError, TypeError):
                flags_val = 0

            is_fin = bool(flags_val & 0x01) or ("F" in flags_str)
            is_syn = bool(flags_val & 0x02) or ("S" in flags_str)
            is_rst = bool(flags_val & 0x04) or ("R" in flags_str)
            is_psh = bool(flags_val & 0x08) or ("P" in flags_str)
            is_ack = bool(flags_val & 0x10) or ("A" in flags_str)
            is_ece = bool(flags_val & 0x40) or ("E" in flags_str)
            is_cwr = bool(flags_val & 0x80) or ("C" in flags_str)

            if is_fin:
                fin_flag = True
                fin_count += 1
            if is_syn:
                syn_flag = True
                syn_count += 1
            if is_rst:
                rst_flag = True
                rst_count += 1
            if is_psh:
                psh_flag = True
            if is_ack:
                ack_flag = True
                ack_count += 1
            if is_ece:
                ece_flag = True
            if is_cwr:
                cwr_flag = True

    features["fin_flag_number"] = 1.0 if fin_flag else 0.0
    features["syn_flag_number"] = 1.0 if syn_flag else 0.0
    features["rst_flag_number"] = 1.0 if rst_flag else 0.0
    features["psh_flag_number"] = 1.0 if psh_flag else 0.0
    features["ack_flag_number"] = 1.0 if ack_flag else 0.0
    features["ece_flag_number"] = 1.0 if ece_flag else 0.0
    features["cwr_flag_number"] = 1.0 if cwr_flag else 0.0

    features["ack_count"] = float(ack_count)
    features["syn_count"] = float(syn_count)
    features["fin_count"] = float(fin_count)
    features["rst_count"] = float(rst_count)

    # ── Protocol / port one-hot indicators ───────────────────────────────
    ports: set[int] = set()
    has_tcp = has_udp = has_arp = has_icmp = has_igmp = has_ipv = has_llc = False

    for pkt in packets:
        if IP in pkt:
            has_ipv = True
        if TCP in pkt:
            has_tcp = True
            ports.add(pkt[TCP].sport)
            ports.add(pkt[TCP].dport)
        if UDP in pkt:
            has_udp = True
            ports.add(pkt[UDP].sport)
            ports.add(pkt[UDP].dport)
        if ARP in pkt:
            has_arp = True
        if ICMP in pkt:
            has_icmp = True
        if IGMP is not None and IGMP in pkt:
            has_igmp = True
        if LLC in pkt:
            has_llc = True

    features["HTTP"] = 1.0 if 80 in ports else 0.0
    features["HTTPS"] = 1.0 if 443 in ports else 0.0
    features["DNS"] = 1.0 if 53 in ports else 0.0
    features["Telnet"] = 1.0 if 23 in ports else 0.0
    features["SMTP"] = 1.0 if 25 in ports else 0.0
    features["SSH"] = 1.0 if 22 in ports else 0.0
    features["IRC"] = 1.0 if 6667 in ports else 0.0
    features["DHCP"] = 1.0 if (67 in ports or 68 in ports) else 0.0

    features["TCP"] = 1.0 if has_tcp else 0.0
    features["UDP"] = 1.0 if has_udp else 0.0
    features["ARP"] = 1.0 if has_arp else 0.0
    features["ICMP"] = 1.0 if has_icmp else 0.0
    features["IGMP"] = 1.0 if has_igmp else 0.0
    features["IPv"] = 1.0 if has_ipv else 0.0
    features["LLC"] = 1.0 if has_llc else 0.0

    return features


def run_capture_cycle(target_ip: str, window_seconds: float = 5.0) -> Dict[str, Any]:
    """
    Capture traffic for a target, extract flows, validate features, run ML inference.

    Returns: {packets_captured, flows_extracted, results: [{source_ip, features, prediction, risk_label}]}
    """
    # ── Get interface from arp_redirect_service (must match the ARP redirect) ─
    redirect_info = arp_redirect_service.get_redirect_info(target_ip)
    if not redirect_info or "iface" not in redirect_info:
        raise ValueError(f"No active redirect info or interface found for {target_ip}")

    iface = redirect_info["iface"]

    # ── Capture packets ──────────────────────────────────────────────────
    try:
        packets = sniff(iface=iface, timeout=window_seconds, filter=f"host {target_ip}")
    except Exception as e:
        logger.error("Sniff failed for %s on %s: %s", target_ip, iface, e)
        return {"packets_captured": 0, "flows_extracted": 0, "results": []}

    if not packets:
        return {"packets_captured": 0, "flows_extracted": 0, "results": []}

    # ── Group into flows by 5-tuple ──────────────────────────────────────
    flows: dict[tuple, list] = defaultdict(list)
    for pkt in packets:
        if IP in pkt:
            src = pkt[IP].src
            dst = pkt[IP].dst
            proto = pkt[IP].proto
            sport = dport = 0
            if TCP in pkt:
                sport, dport = pkt[TCP].sport, pkt[TCP].dport
            elif UDP in pkt:
                sport, dport = pkt[UDP].sport, pkt[UDP].dport
            flow_key = (src, dst, sport, dport, proto)
            flows[flow_key].append(pkt)

    # ── Extract features and predict for each flow (>= 2 packets) ────────
    results: list[dict] = []

    for flow_key, flow_packets in flows.items():
        if len(flow_packets) < 2:
            continue

        src_ip = flow_key[0]
        features = extract_flow_features(flow_packets)

        # ── Runtime safety check: warn about any missing keys ────────
        missing = [col for col in FEATURE_COLUMNS if col not in features]
        if missing:
            logger.warning(
                "MISSING FEATURES in flow dict (will default to 0.0 in predict): %s",
                missing,
            )

        # ── Run ML prediction ────────────────────────────────────────
        try:
            prediction_result = inference.predict(features)
        except Exception as e:
            prediction_result = {"prediction": "Error", "confidence": 0.0, "error": str(e)}

        # ── Compute risk_label ───────────────────────────────────────
        pred_label = prediction_result.get("prediction", "Unknown")
        confidence = prediction_result.get("confidence", 0.0)
        if pred_label == "Benign":
            risk_label = "Low"
        elif confidence >= 0.9:
            risk_label = "Critical"
        elif confidence >= 0.7:
            risk_label = "High"
        elif confidence >= 0.4:
            risk_label = "Medium"
        else:
            risk_label = "Low"

        results.append({
            "source_ip": src_ip,
            "features": features,  # full 39-key dict
            "prediction": prediction_result,  # {prediction, confidence, top_features}
            "risk_label": risk_label,
        })

    return {
        "packets_captured": len(packets),
        "flows_extracted": len(flows),
        "results": results,
    }
