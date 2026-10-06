"""
app/routers/system.py

System information and per-user settings endpoints.
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.user import User, get_db
from app.services.auth_service import get_current_user

logger = logging.getLogger("kronos")

router = APIRouter(tags=["system"])

_MODEL_DIR = Path(__file__).resolve().parent.parent / "services" / "ml_model"


# ── GET /system/model-info ─────────────────────────────────────────────────────


@router.get("/system/model-info")
def model_info() -> dict[str, Any]:
    """Return key facts about the deployed XGBoost model artifacts."""
    # Feature count
    feature_columns_path = _MODEL_DIR / "feature_columns.json"
    try:
        with open(feature_columns_path, encoding="utf-8") as f:
            features: list[str] = json.load(f)
        n_features = len(features)
    except Exception:
        n_features = 0
        features = []

    # Hyperparams
    hyperparams: dict[str, Any] = {}
    hp_path = _MODEL_DIR / "best_hyperparams.json"
    if hp_path.exists():
        try:
            with open(hp_path, encoding="utf-8") as f:
                hyperparams = json.load(f)
        except Exception:
            pass

    # Derive model version/timestamp from artifact filename
    model_timestamp = "unknown"
    model_version = "unknown"
    for p in _MODEL_DIR.glob("stage1_binary_*.json"):
        # e.g. stage1_binary_20260927_184325.json
        parts = p.stem.split("_")
        if len(parts) >= 4:
            model_timestamp = f"{parts[2]}_{parts[3]}"
            model_version = f"XGBoost-2stage-{model_timestamp}"
        break

    # Label mappings
    label_mapping: dict[str, Any] = {}
    lm_path = _MODEL_DIR / "stage2_label_mapping.json"
    if lm_path.exists():
        try:
            with open(lm_path, encoding="utf-8") as f:
                label_mapping = json.load(f)
        except Exception:
            pass

    return {
        "model_version": model_version,
        "model_timestamp": model_timestamp,
        "n_features": n_features,
        "stage1_hyperparams": hyperparams.get("stage1", {}),
        "stage2_hyperparams": hyperparams.get("stage2", {}),
        "attack_classes": list(label_mapping.values()),
        "n_attack_classes": len(label_mapping),
        "dataset": "CICIoT2023",
        "architecture": "Two-stage XGBoost (binary → multiclass) with Platt calibration and SHAP explainability",
    }


# ── GET /user/settings ─────────────────────────────────────────────────────────


class UserSettings(BaseModel):
    email_alerts_critical: bool
    flow_window_seconds: int
    risk_threshold: str


@router.get("/user/settings", response_model=UserSettings)
def get_user_settings(current_user: User = Depends(get_current_user)) -> UserSettings:
    """Return the current user's monitoring and notification settings."""
    return UserSettings(
        email_alerts_critical=bool(current_user.email_alerts_critical),
        flow_window_seconds=current_user.flow_window_seconds or 5,
        risk_threshold=current_user.risk_threshold or "Medium",
    )


# ── POST /user/settings ────────────────────────────────────────────────────────


class UpdateUserSettingsRequest(BaseModel):
    email_alerts_critical: bool | None = None
    flow_window_seconds: int | None = None
    risk_threshold: str | None = None


@router.post("/user/settings", response_model=UserSettings)
def update_user_settings(
    payload: UpdateUserSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettings:
    """Update the authenticated user's monitoring and notification settings."""
    if payload.email_alerts_critical is not None:
        current_user.email_alerts_critical = payload.email_alerts_critical
    if payload.flow_window_seconds is not None:
        if not (1 <= payload.flow_window_seconds <= 120):
            raise HTTPException(status_code=400, detail="flow_window_seconds must be between 1 and 120.")
        current_user.flow_window_seconds = payload.flow_window_seconds
    if payload.risk_threshold is not None:
        if payload.risk_threshold not in ("Medium", "High", "Critical"):
            raise HTTPException(status_code=400, detail="risk_threshold must be 'Medium', 'High', or 'Critical'.")
        current_user.risk_threshold = payload.risk_threshold
    db.commit()
    db.refresh(current_user)
    return UserSettings(
        email_alerts_critical=bool(current_user.email_alerts_critical),
        flow_window_seconds=current_user.flow_window_seconds or 5,
        risk_threshold=current_user.risk_threshold or "Medium",
    )
