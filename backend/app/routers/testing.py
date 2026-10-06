"""Testing endpoint for realistic presets and manual pipeline execution."""

import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.agents.orchestrator import run_pipeline
from app.models.user import get_db
from app.services.incident_service import save_incident
from app.services.logger_service import log_exchange
from app.services.ml_model import inference

logger = logging.getLogger("kronos")

router = APIRouter(prefix="/testing", tags=["testing"])

FEATURE_COLUMNS_PATH = (
    Path(__file__).resolve().parent.parent / "services" / "ml_model" / "feature_columns.json"
)

with open(FEATURE_COLUMNS_PATH, encoding="utf-8") as f:
    FEATURE_COLUMNS: list[str] = json.load(f)

# Baseline values derived from the CIC IoT 2023 dataset statistics.
# These hand-tuned approximations are designed for testing and simulation purposes,
# not real captured production samples.
_BENIGN_BASELINE: dict[str, float] = {
    "Header_Length": 31.88758,
    "Protocol Type": 21.4727,
    "Time_To_Live": 87.31387,
    "Rate": 21301.887,
    "fin_flag_number": 0.3211,
    "syn_flag_number": 0.20378,
    "rst_flag_number": -1.21456,
    "psh_flag_number": 1.16726,
    "ack_flag_number": 1.1552,
    "ece_flag_number": 0.00005,
    "cwr_flag_number": 0.000027,
    "ack_count": 10.38388,
    "syn_count": 19.95,
    "fin_count": 6.87334,
    "rst_count": 7.86128,
    "HTTP": 0.55673,
    "HTTPS": 1.14896,
    "DNS": 0.12176,
    "Telnet": 0.000017,
    "SMTP": 0.000018,
    "SSH": 0.00037,
    "IRC": 0.000028,
    "TCP": 0.8045,
    "UDP": 0.23457,
    "DHCP": 0.0003,
    "ARP": 0.00486,
    "ICMP": -1.48424,
    "IGMP": 0.000035,
    "IPv": 0.99514,
    "LLC": 0.99514,
    "Tot sum": 14590.418,
    "Min": 93.59,
    "Max": 4093.664,
    "AVG": 1646.139,
    "Std": 775.6367,
    "Tot size": 769.0163,
    "IAT": 0.0238,
    "Number": 1.0,
    "Variance": -2491711.0,
}


def _build_preset_features(overrides: dict[str, float]) -> dict[str, float]:
    """Construct a full feature dict covering every feature in feature_columns.json."""
    features = {col: _BENIGN_BASELINE.get(col, 0.0) for col in FEATURE_COLUMNS}
    features.update(overrides)
    return {col: float(features[col]) for col in FEATURE_COLUMNS}


# Pre-computed realistic test presets with 100% feature coverage
PRESETS: list[dict[str, Any]] = [
    {
        "name": "Benign Traffic",
        "description": (
            "Normal low-rate IoT baseline communication with standard TTL, "
            "typical flow duration, and expected HTTP/HTTPS ratios."
        ),
        "features": _build_preset_features({
            "Header_Length": 32.0,
            "Protocol Type": 6.0,
            "Time_To_Live": 64.0,
            "Rate": 15.5,
            "fin_flag_number": 0.0,
            "syn_flag_number": 0.0,
            "rst_flag_number": 0.0,
            "psh_flag_number": 0.1,
            "ack_flag_number": 0.9,
            "ack_count": 12.0,
            "syn_count": 1.0,
            "HTTP": 0.0,
            "HTTPS": 1.0,
            "TCP": 1.0,
            "UDP": 0.0,
            "IAT": 0.065,
            "Tot sum": 14500.0,
            "Min": 54.0,
            "Max": 1420.0,
            "AVG": 680.0,
            "Std": 420.0,
            "Tot size": 680.0,
            "Number": 22.0,
        }),
    },
    {
        "name": "DDoS-like",
        "description": (
            "High-rate TCP SYN flood inundation featuring excessive packet rate, "
            "near-zero inter-arrival time (IAT), and high SYN flag count."
        ),
        "features": _build_preset_features({
            "Header_Length": 20.0,
            "Protocol Type": 6.0,
            "Time_To_Live": 128.0,
            "Rate": 120000.0,
            "syn_flag_number": 1.0,
            "syn_count": 1500.0,
            "ack_flag_number": 0.0,
            "ack_count": 0.0,
            "fin_flag_number": 0.0,
            "rst_flag_number": 0.0,
            "TCP": 1.0,
            "UDP": 0.0,
            "HTTP": 0.0,
            "HTTPS": 0.0,
            "IAT": 0.00005,
            "Tot size": 44.0,
            "Min": 40.0,
            "Max": 60.0,
            "AVG": 44.0,
            "Std": 1.5,
            "Number": 95.0,
            "Tot sum": 25000.0,
        }),
    },
    {
        "name": "Port Scan (Recon)-like",
        "description": (
            "Network service and OS reconnaissance scan utilizing sequential SYN probes "
            "to detect open ports and map IoT network attack surface."
        ),
        "features": _build_preset_features({
            "Protocol Type": 6.0,
            "Rate": 20.0,
            "syn_flag_number": 1.0,
            "ack_flag_number": 0.0,
            "rst_flag_number": 0.0,
            "HTTP": 0.0,
            "HTTPS": 0.0,
            "DNS": 0.0,
            "TCP": 1.0,
            "UDP": 0.0,
            "ICMP": 0.0,
        }),
    },
    {
        "name": "Mirai-like",
        "description": (
            "High-rate Mirai IoT botnet UDP flood profile with repetitive payload characteristics "
            "and saturated transmission volume."
        ),
        "features": _build_preset_features({
            "Header_Length": 42.0,
            "Protocol Type": 17.0,
            "Time_To_Live": 64.0,
            "Rate": 85000.0,
            "syn_flag_number": 0.0,
            "syn_count": 0.0,
            "ack_flag_number": 0.0,
            "ack_count": 0.0,
            "UDP": 1.0,
            "TCP": 0.0,
            "HTTP": 0.0,
            "HTTPS": 0.0,
            "Tot sum": 55500.0,
            "Min": 500.0,
            "Max": 555.0,
            "AVG": 540.0,
            "Std": 15.0,
            "Tot size": 540.0,
            "IAT": 0.0001,
            "Number": 95.0,
            "Variance": 225.0,
        }),
    },
]


class TestRunPayload(BaseModel):
    """Payload for executing a test detection flow."""

    preset_name: str | None = None
    features: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def check_input_present(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")
        if not data.get("preset_name") and not data.get("features"):
            raise ValueError("Provide either 'preset_name' or 'features'.")
        return data


@router.get("/presets")
async def get_test_presets() -> list[dict[str, Any]]:
    """Return realistic test presets covering all model feature columns."""
    return PRESETS


@router.post("/run")
async def run_test_incident(
    payload: TestRunPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute the multi-agent incident pipeline for a preset or custom feature payload."""
    endpoint_started_at = time.perf_counter()
    request_id = getattr(request.state, "request_id", str(uuid4()))

    features_to_run: dict[str, float] = {}

    if payload.preset_name:
        preset_match = next(
            (p for p in PRESETS if p["name"].lower() == payload.preset_name.lower().strip()),
            None,
        )
        if not preset_match:
            raise HTTPException(
                status_code=404,
                detail=f"Preset '{payload.preset_name}' not found. Available presets: "
                + ", ".join(f"'{p['name']}'" for p in PRESETS),
            )
        features_to_run = dict(preset_match["features"])
    elif payload.features:
        if not isinstance(payload.features, dict) or not payload.features:
            raise HTTPException(
                status_code=422,
                detail="Features must be a non-empty object of numeric flow values.",
            )
        for k, v in payload.features.items():
            if not isinstance(k, str) or not k.strip():
                raise HTTPException(
                    status_code=422,
                    detail="Feature names must be non-empty strings.",
                )
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise HTTPException(
                    status_code=422,
                    detail=f"Feature '{k}' must be a numeric value.",
                )
            if not math.isfinite(v):
                raise HTTPException(
                    status_code=422,
                    detail=f"Feature '{k}' must be finite.",
                )
            features_to_run[k] = float(v)
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'preset_name' or 'features'.",
        )

    # Execute exactly the same pipeline code path as /incident
    detector_result = await run_in_threadpool(inference.predict, features_to_run)
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

    # Persist with source="test" so Dashboard can distinguish from live traffic
    save_incident(db, incident_report, source="test", source_ip="192.0.2.1 (test)")

    log_exchange(
        request_id=request_id,
        endpoint="/testing/run",
        request_data=payload.model_dump(mode="json"),
        response_data=incident_report,
        latency_ms=endpoint_latency_ms,
        status=200,
    )

    return incident_report
