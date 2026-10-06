"""Incident endpoints: save, list, and stats for the KRONOS incident feed."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.agents.orchestrator import run_pipeline
from app.models.schemas import NetworkFlowRequest
from app.models.user import IncidentRecord, get_db
from app.services.incident_service import save_incident
from app.services.logger_service import log_exchange
from app.services.ml_model import inference

logger = logging.getLogger("kronos")

router = APIRouter(tags=["incident"])


# ── POST /incident ─────────────────────────────────────────────────────────────


@router.post("/incident")
async def create_incident(
    sample: NetworkFlowRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Detect a network flow, run the full agent pipeline, and persist the result."""
    endpoint_started_at = time.perf_counter()
    request_id = getattr(request.state, "request_id", str(uuid4()))
    detector_result = await run_in_threadpool(inference.predict, sample.root)
    detection_result = {
        **detector_result,
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc),
    }
    incident_report = run_pipeline(detection_result)
    endpoint_latency_ms = round(
        (time.perf_counter() - endpoint_started_at) * 1000,
        2,
    )

    # Save with source="manual_simulate" (this is the "Quick Simulate" path)
    save_incident(db, incident_report, source="manual_simulate", source_ip="192.0.2.1 (simulated)")

    log_exchange(
        request_id=request_id,
        endpoint="/incident",
        request_data=sample.root,
        response_data=incident_report,
        latency_ms=endpoint_latency_ms,
        status=200,
    )
    return incident_report


# ── GET /incidents ─────────────────────────────────────────────────────────────


@router.get("/incidents")
def list_incidents(
    source: str | None = Query(default=None, description="Filter by source: live|test|manual_simulate"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Return a compact list of incidents, newest first.

    Each item includes: id, request_id, timestamp, source_ip, attack_type,
    risk_label, confidence, mitigated, source, evidence_summary, pipeline_latency_ms.
    """
    query = db.query(IncidentRecord).order_by(IncidentRecord.timestamp.desc())
    if source:
        query = query.filter(IncidentRecord.source == source)
    records = query.limit(limit).all()

    return [_to_summary(r) for r in records]


# ── GET /incidents/stats ───────────────────────────────────────────────────────


@router.get("/incidents/stats")
def incident_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Return aggregate statistics over stored incidents:
      - total_incidents
      - high_critical_count  (risk_label in High | Critical)
      - avg_pipeline_latency_ms
    """
    total = db.query(func.count(IncidentRecord.id)).scalar() or 0

    high_critical = (
        db.query(func.count(IncidentRecord.id))
        .filter(IncidentRecord.risk_label.in_(["High", "Critical"]))
        .scalar()
        or 0
    )

    avg_latency_row = db.query(
        func.avg(IncidentRecord.pipeline_latency_ms)
    ).scalar()
    avg_latency = round(float(avg_latency_row), 2) if avg_latency_row is not None else 0.0

    return {
        "total_incidents": total,
        "high_critical_count": high_critical,
        "avg_pipeline_latency_ms": avg_latency,
    }


# ── GET /incidents/{id} ────────────────────────────────────────────────────────


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return the full pipeline report for a single incident."""
    record = db.query(IncidentRecord).filter(IncidentRecord.id == incident_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Incident not found.")
    result = _to_summary(record)
    if record.full_report:
        try:
            result["full_report"] = json.loads(record.full_report)
        except json.JSONDecodeError:
            result["full_report"] = None
    return result


# ── helpers ────────────────────────────────────────────────────────────────────


def _to_summary(r: IncidentRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "request_id": r.request_id,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "source_ip": r.source_ip,
        "attack_type": r.attack_type,
        "risk_label": r.risk_label,
        "risk_score": r.risk_score,
        "confidence": r.confidence,
        "mitigated": r.mitigated,
        "source": r.source,
        "evidence_summary": r.evidence_summary,
        "pipeline_latency_ms": r.pipeline_latency_ms,
        "occurrence_count": getattr(r, "occurrence_count", 1) or 1,
        "last_seen_at": r.last_seen_at.isoformat() if getattr(r, "last_seen_at", None) else None,
    }