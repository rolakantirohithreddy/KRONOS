"""Tests for network-flow prediction, request validation, and ML model inference."""

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from starlette.testclient import TestClient

from app.main import app
from app.services.ml_model import inference
from app.services.ml_model.inference import FEATURE_COLUMNS, STAGE2_LABEL_MAPPING

VALID_PREDICTIONS = set(STAGE2_LABEL_MAPPING.values()) | {"Benign"}

SAMPLE_FLOW = {"Rate": 10000.0, "syn_count": 500.0, "syn_flag_number": 1.0, "Protocol Type": 6.0}

BENIGN_SAMPLE_PATH = Path(__file__).parent / "benign_sample.json"
with open(BENIGN_SAMPLE_PATH) as f:
    BENIGN_SAMPLE = json.load(f)


def test_predict_returns_expected_shape_and_latency() -> None:
    """Verify a valid flow returns a prediction, explanation, and metadata."""
    with TestClient(app) as client:
        response = client.post("/predict", json=SAMPLE_FLOW)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "prediction",
        "confidence",
        "top_features",
        "latency_ms",
        "request_id",
        "timestamp",
    }
    assert payload["prediction"] in VALID_PREDICTIONS
    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["latency_ms"] > 0.0
    assert 0 <= len(payload["top_features"]) <= 5
    for feature in payload["top_features"]:
        assert set(feature) == {"feature", "value", "shap_value", "direction"}
        assert feature["feature"] in FEATURE_COLUMNS
        assert feature["direction"] in {"increases risk", "decreases risk"}
    UUID(payload["request_id"])
    assert datetime.fromisoformat(payload["timestamp"])
    assert response.headers["X-Request-ID"] == payload["request_id"]


def test_predict_benign_input() -> None:
    """Verify benign-like flow returns prediction='Benign' with empty top_features."""
    with TestClient(app) as client:
        response = client.post("/predict", json=BENIGN_SAMPLE)

    assert response.status_code == 200
    payload = response.json()
    assert payload["prediction"] == "Benign"
    assert payload["top_features"] == []
    assert 0.0 <= payload["confidence"] <= 1.0


def test_predict_attack_input() -> None:
    """Verify attack-like flow returns attack class with top_features."""
    with TestClient(app) as client:
        response = client.post("/predict", json=SAMPLE_FLOW)

    assert response.status_code == 200
    payload = response.json()
    assert payload["prediction"] in STAGE2_LABEL_MAPPING.values()
    assert len(payload["top_features"]) > 0
    assert 0.0 <= payload["confidence"] <= 1.0


def test_direct_inference_predict_contracts() -> None:
    """Directly test inference.predict() for both benign and attack inputs."""
    benign_res = inference.predict(BENIGN_SAMPLE)
    assert benign_res["prediction"] == "Benign"
    assert benign_res["top_features"] == []
    assert isinstance(benign_res["confidence"], float)

    attack_res = inference.predict(SAMPLE_FLOW)
    assert attack_res["prediction"] in STAGE2_LABEL_MAPPING.values()
    assert 1 <= len(attack_res["top_features"]) <= 5
    for item in attack_res["top_features"]:
        assert item["feature"] in FEATURE_COLUMNS
        assert isinstance(item["value"], float)
        assert isinstance(item["shap_value"], float)
        assert item["direction"] in {"increases risk", "decreases risk"}


def test_predict_rejects_empty_feature_map() -> None:
    """Return a helpful 422 response when no flow features are provided."""
    with TestClient(app) as client:
        response = client.post("/predict", json={})

    assert response.status_code == 422
    assert "at least one" in response.json()["detail"].lower()


def test_predict_rejects_wrong_feature_type() -> None:
    """Return a 422 response instead of crashing on nonnumeric features."""
    with TestClient(app) as client:
        response = client.post("/predict", json={"packet_rate": "fast"})

    assert response.status_code == 422
    assert "must be a number" in response.json()["detail"].lower()