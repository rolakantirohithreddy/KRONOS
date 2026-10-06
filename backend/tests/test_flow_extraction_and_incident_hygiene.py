"""
Tests for flow extraction (39 feature completeness) and incident hygiene
(deduplication, cooldown window, threshold filtering, and benign skipping).
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from scapy.all import IP, TCP, Ether
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.user import Base, IncidentRecord
from app.services.flow_extractor import (
    FEATURE_COLUMNS,
    extract_flow_features,
)
from app.services.incident_service import (
    save_incident,
    DEDUP_COOLDOWN_SECONDS,
)

# In-memory SQLite DB for isolation
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ── TEST 1: Feature dict completeness (all 39 keys populated) ────────────────


def test_extract_flow_features_populates_all_39_keys():
    """Verify that extract_flow_features computes all 39 model feature keys without missing any."""
    p1 = Ether() / IP(src="192.168.1.50", dst="192.168.1.1", proto=6, ttl=64) / TCP(sport=50000, dport=80, flags="S")
    p1.time = time.time()

    p2 = Ether() / IP(src="192.168.1.50", dst="192.168.1.1", proto=6, ttl=64) / TCP(sport=50000, dport=80, flags="A")
    p2.time = p1.time + 0.02

    features = extract_flow_features([p1, p2])

    assert isinstance(features, dict)
    assert len(features) == 39

    missing = [k for k in FEATURE_COLUMNS if k not in features]
    assert missing == [], f"Missing required features: {missing}"

    # Verify specific feature values are properly computed
    assert features["Number"] == 2.0
    assert features["HTTP"] == 1.0
    assert features["HTTPS"] == 0.0
    assert features["TCP"] == 1.0
    assert features["UDP"] == 0.0
    assert features["syn_count"] == 1.0
    assert features["ack_count"] == 1.0
    assert features["syn_flag_number"] == 1.0
    assert features["ack_flag_number"] == 1.0
    assert features["Rate"] > 0.0
    assert features["IAT"] > 0.0


def test_feature_dict_sent_to_predict_has_all_39_keys():
    """Confirm the feature dict sent to inference.predict during capture cycle has all 39 keys."""
    p1 = Ether() / IP(src="10.0.0.5", dst="10.0.0.1", proto=6) / TCP(sport=443, dport=40000, flags="SA")
    p1.time = 1000.0
    p2 = Ether() / IP(src="10.0.0.5", dst="10.0.0.1", proto=6) / TCP(sport=443, dport=40000, flags="A")
    p2.time = 1000.05

    captured_sample = None

    def fake_predict(sample):
        nonlocal captured_sample
        captured_sample = sample
        return {"prediction": "Benign", "confidence": 0.99, "top_features": []}

    with patch("app.services.arp_redirect_service.get_redirect_info", return_value={"iface": "eth0"}), \
         patch("app.services.flow_extractor.sniff", return_value=[p1, p2]), \
         patch("app.services.ml_model.inference.predict", side_effect=fake_predict):

        from app.services.flow_extractor import run_capture_cycle

        result = run_capture_cycle("10.0.0.5", window_seconds=1.0)
        assert result["packets_captured"] == 2
        assert len(result["results"]) == 1

        assert captured_sample is not None
        missing = [col for col in FEATURE_COLUMNS if col not in captured_sample]
        assert missing == [], f"Keys missing from predict input: {missing}"
        assert len(captured_sample) == 39


# ── TEST 2: Benign flow is NOT inserted as an incident ───────────────────────


def test_benign_classified_flow_not_inserted_as_incident(db):
    """Confirm that a live-sourced Benign prediction is skipped and not saved to DB."""
    pipeline_result = {
        "detection": {
            "prediction": "Benign",
            "confidence": 0.95,
            "timestamp": datetime.now(timezone.utc),
        },
        "risk_assessment": {
            "risk_label": "Low",
            "risk_score": 5.0,
        },
        "evidence": {"evidence_statements": ["Normal benign traffic"]},
        "agent_latencies_ms": {"total": 12.0},
        "request_id": "req-benign-1",
    }

    record = save_incident(db, pipeline_result, source="live", source_ip="192.168.1.100")

    assert record is None
    count = db.query(IncidentRecord).count()
    assert count == 0


def test_low_risk_flow_below_threshold_not_inserted(db):
    """Confirm that a live-sourced attack with Low risk (below Medium threshold) is skipped."""
    pipeline_result = {
        "detection": {
            "prediction": "DDOS-SYN_FLOOD",
            "confidence": 0.35,
            "timestamp": datetime.now(timezone.utc),
        },
        "risk_assessment": {
            "risk_label": "Low",
            "risk_score": 35.0,
        },
        "evidence": {"evidence_statements": ["Low confidence detection"]},
        "agent_latencies_ms": {"total": 10.0},
        "request_id": "req-low-1",
    }

    record = save_incident(db, pipeline_result, source="live", source_ip="192.168.1.100")

    assert record is None
    count = db.query(IncidentRecord).count()
    assert count == 0


# ── TEST 3: Deduplication and Cooldown Window ────────────────────────────────


def test_deduplication_increments_occurrence_count(db):
    """Confirm two same-source same-prediction live flows within cooldown result in 1 row with occurrence_count=2."""
    now = datetime.now(timezone.utc)

    pipeline_result_1 = {
        "detection": {
            "prediction": "DNS_SPOOFING",
            "confidence": 0.85,
            "timestamp": now,
        },
        "risk_assessment": {
            "risk_label": "High",
            "risk_score": 85.0,
        },
        "evidence": {"evidence_statements": ["Spoofed DNS response"]},
        "agent_latencies_ms": {"total": 15.0},
        "request_id": "req-attack-1",
    }

    # First occurrence
    record_1 = save_incident(db, pipeline_result_1, source="live", source_ip="192.168.1.105")
    assert record_1 is not None
    assert record_1.occurrence_count == 1
    assert db.query(IncidentRecord).count() == 1

    # Second occurrence (same target, same attack, 5 seconds later - within 60s cooldown)
    pipeline_result_2 = {
        "detection": {
            "prediction": "DNS_SPOOFING",
            "confidence": 0.90,
            "timestamp": now + timedelta(seconds=5),
        },
        "risk_assessment": {
            "risk_label": "Critical",
            "risk_score": 90.0,
        },
        "evidence": {"evidence_statements": ["Second spoofed response"]},
        "agent_latencies_ms": {"total": 14.0},
        "request_id": "req-attack-2",
    }

    record_2 = save_incident(db, pipeline_result_2, source="live", source_ip="192.168.1.105")

    # Should update existing record instead of inserting new
    assert record_2 is not None
    assert record_2.id == record_1.id
    assert record_2.occurrence_count == 2
    assert record_2.confidence == 0.90  # took max confidence
    assert db.query(IncidentRecord).count() == 1


def test_different_attack_or_ip_creates_separate_records(db):
    """Confirm different source IP or different attack creates a new incident row."""
    now = datetime.now(timezone.utc)

    res_1 = {
        "detection": {"prediction": "DDOS-SYN_FLOOD", "confidence": 0.88, "timestamp": now},
        "risk_assessment": {"risk_label": "High", "risk_score": 88.0},
        "evidence": {}, "agent_latencies_ms": {}, "request_id": "req-1",
    }
    # Different IP
    res_2 = {
        "detection": {"prediction": "DDOS-SYN_FLOOD", "confidence": 0.88, "timestamp": now},
        "risk_assessment": {"risk_label": "High", "risk_score": 88.0},
        "evidence": {}, "agent_latencies_ms": {}, "request_id": "req-2",
    }
    # Different Attack
    res_3 = {
        "detection": {"prediction": "RECON-PORTSCAN", "confidence": 0.80, "timestamp": now},
        "risk_assessment": {"risk_label": "High", "risk_score": 80.0},
        "evidence": {}, "agent_latencies_ms": {}, "request_id": "req-3",
    }

    save_incident(db, res_1, source="live", source_ip="192.168.1.10")
    save_incident(db, res_2, source="live", source_ip="192.168.1.20")
    save_incident(db, res_3, source="live", source_ip="192.168.1.10")

    assert db.query(IncidentRecord).count() == 3
