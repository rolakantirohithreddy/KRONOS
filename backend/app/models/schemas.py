"""Pydantic models shared by the KRONOS API and detector."""

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, RootModel, model_validator


PredictionLabel = Literal[
    "DDoS",
    "DoS",
    "Recon",
    "Mirai",
    "Spoofing",
    "BruteForce",
    "Benign",
]
FeatureDirection = Literal["increases risk", "decreases risk"]


class NetworkFlowRequest(RootModel[dict[str, float]]):
    """Validate a non-empty JSON object of finite numeric flow features."""

    @model_validator(mode="before")
    @classmethod
    def validate_features(cls, value: Any) -> Any:
        """Reject missing, empty, or nonnumeric feature maps with clear errors."""
        if not isinstance(value, dict):
            raise ValueError("Request body must be an object of numeric flow features.")
        if not value:
            raise ValueError("Provide at least one network flow feature.")

        for feature_name, feature_value in value.items():
            if not isinstance(feature_name, str) or not feature_name.strip():
                raise ValueError("Feature names must be non-empty strings.")
            if isinstance(feature_value, bool) or not isinstance(
                feature_value, (int, float)
            ):
                raise ValueError(f"Feature '{feature_name}' must be a number.")
            if not math.isfinite(feature_value):
                raise ValueError(f"Feature '{feature_name}' must be finite.")
        return value


class TopFeature(BaseModel):
    """Explain one feature's contribution to the predicted class."""

    feature: str
    value: float
    shap_value: float
    direction: FeatureDirection


class DetectorResponse(BaseModel):
    """Represent the prediction payload returned by the detector."""

    prediction: str
    confidence: float
    top_features: list[TopFeature]
    latency_ms: float = 0.0


class PredictResponse(DetectorResponse):
    """Represent a detector result enriched with API request metadata."""

    request_id: str
    timestamp: datetime


class HealthResponse(BaseModel):
    """Represent the service health check response."""

    status: Literal["ok"]
    timestamp: datetime
    version: str


class ErrorResponse(BaseModel):
    """Represent a concise client-facing request validation error."""

    model_config = ConfigDict(extra="forbid")

    detail: str