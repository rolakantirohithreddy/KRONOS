"""
app/services/incident_service.py

Central service for saving incident pipeline results to the DB,
sending critical-alert emails, and retrieving incident records.

Includes SOC-style alert hygiene:
- Threshold filtering: only persist incidents at or above a configurable risk level.
- Deduplication/cooldown: same source_ip + same attack_type within a cooldown
  window updates the existing row's occurrence_count instead of inserting a new one.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import IncidentRecord, User
from app.services.email_service import send_critical_alert_email

logger = logging.getLogger("kronos")

# ── configurable thresholds ──────────────────────────────────────────────
# Minimum risk_label required for an incident to be persisted.
# Ordered Low < Medium < High < Critical.
RISK_LEVEL_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
MIN_RISK_LEVEL: str = "Medium"  # default threshold

# Cooldown window for deduplication (seconds).
DEDUP_COOLDOWN_SECONDS: int = 60


def _get_min_risk_level(db: Session | None = None) -> str:
    """Read the configured risk threshold from the DB, falling back to MIN_RISK_LEVEL."""
    if db is not None:
        try:
            user = db.query(User).filter(User.risk_threshold.isnot(None)).first()
            if user and user.risk_threshold in RISK_LEVEL_ORDER:
                return user.risk_threshold
        except Exception:
            pass
    return MIN_RISK_LEVEL


def _meets_threshold(risk_label: str, min_level: str = MIN_RISK_LEVEL) -> bool:
    """Return True if risk_label is at or above min_level."""
    return RISK_LEVEL_ORDER.get(risk_label, 0) >= RISK_LEVEL_ORDER.get(min_level, 1)


def save_incident(
    db: Session,
    pipeline_result: dict[str, Any],
    source: str,
    source_ip: str | None = None,
) -> IncidentRecord | None:
    """
    Persist a pipeline result as an IncidentRecord with SOC-style hygiene.

    For source="live":
      - Skips Benign predictions entirely.
      - Skips predictions below MIN_RISK_LEVEL (or configured user threshold).
      - Deduplicates: if an existing incident with the same source_ip + attack_type
        exists within DEDUP_COOLDOWN_SECONDS, increments occurrence_count instead
        of inserting a new row.

    For source="test" or "manual_simulate":
      - Always persists (no threshold/dedup filtering).

    Returns the saved/updated IncidentRecord, or None if filtered out.
    """
    detection = pipeline_result.get("detection", {})
    risk = pipeline_result.get("risk_assessment") or {}
    evidence = pipeline_result.get("evidence") or {}
    latencies = pipeline_result.get("agent_latencies_ms") or {}

    attack_type: str = detection.get("prediction", "Unknown")
    confidence: float = float(detection.get("confidence", 0.0))
    risk_label: str = risk.get("risk_label", "Low")
    risk_score: float = float(risk.get("risk_score", 0.0))

    # ── Live-source hygiene ───────────────────────────────────────────
    if source == "live":
        if attack_type == "Benign":
            return None
        min_level = _get_min_risk_level(db)
        if not _meets_threshold(risk_label, min_level):
            logger.debug(
                "Incident below threshold (%s < %s), skipping: %s from %s",
                risk_label, min_level, attack_type, source_ip,
            )
            return None

        # Deduplication: check for recent same-source same-attack incident
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=DEDUP_COOLDOWN_SECONDS)
        existing = (
            db.query(IncidentRecord)
            .filter(
                IncidentRecord.source == "live",
                IncidentRecord.source_ip == source_ip,
                IncidentRecord.attack_type == attack_type,
                IncidentRecord.timestamp >= cutoff,
            )
            .order_by(IncidentRecord.timestamp.desc())
            .first()
        )
        if existing:
            existing.occurrence_count = (existing.occurrence_count or 1) + 1
            existing.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
            existing.confidence = max(existing.confidence, confidence)
            db.commit()
            db.refresh(existing)
            logger.info(
                "Dedup: updated incident #%d (%s from %s) occurrence_count=%d",
                existing.id, attack_type, source_ip, existing.occurrence_count,
            )
            return existing

    # ── Build and persist new record ──────────────────────────────────
    evidence_statements: list[str] = (
        evidence.get("evidence_statements", []) if isinstance(evidence, dict) else []
    )
    evidence_summary: str | None = evidence_statements[0] if evidence_statements else None
    total_latency: float = float(latencies.get("total", 0.0))

    raw_ts = detection.get("timestamp")
    if isinstance(raw_ts, datetime):
        ts = raw_ts.replace(tzinfo=None)
    elif isinstance(raw_ts, str):
        try:
            ts = datetime.fromisoformat(raw_ts).replace(tzinfo=None)
        except ValueError:
            ts = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        ts = datetime.now(timezone.utc).replace(tzinfo=None)

    request_id: str = pipeline_result.get("request_id", "")

    record = IncidentRecord(
        request_id=request_id,
        timestamp=ts,
        source_ip=source_ip,
        attack_type=attack_type,
        confidence=confidence,
        risk_label=risk_label,
        risk_score=risk_score,
        mitigated=False,
        source=source,
        evidence_summary=evidence_summary,
        full_report=json.dumps(pipeline_result, default=str),
        pipeline_latency_ms=total_latency,
        occurrence_count=1,
        last_seen_at=ts,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    if risk_label == "Critical":
        _notify_critical_subscribers(db, record)

    return record


def _notify_critical_subscribers(db: Session, record: IncidentRecord) -> None:
    """Email all users who opted in to critical-incident alerts."""
    try:
        users = db.query(User).filter(User.email_alerts_critical.is_(True)).all()
        ts_str = record.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        for user in users:
            send_critical_alert_email(
                recipient=user.email,
                attack_type=record.attack_type,
                source_ip=record.source_ip,
                timestamp=ts_str,
            )
    except Exception as exc:
        logger.error("Failed to dispatch critical-alert emails: %s", exc, exc_info=True)
