"""Integration tests for the testing panel endpoints."""

import json
from pathlib import Path
from starlette.testclient import TestClient

from app.main import app

FEATURE_COLUMNS_PATH = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "services"
    / "ml_model"
    / "feature_columns.json"
)

with open(FEATURE_COLUMNS_PATH, encoding="utf-8") as f:
    FEATURE_COLUMNS = json.load(f)


def test_get_presets_covers_every_feature() -> None:
    """Verify GET /testing/presets returns all presets covering 100% of feature_columns."""
    with TestClient(app) as client:
        response = client.get("/testing/presets")

    assert response.status_code == 200
    presets = response.json()
    assert isinstance(presets, list)
    assert len(presets) >= 4

    preset_names = {p["name"] for p in presets}
    assert "Benign Traffic" in preset_names
    assert "DDoS-like" in preset_names
    assert "Port Scan (Recon)-like" in preset_names
    assert "Mirai-like" in preset_names

    expected_feature_set = set(FEATURE_COLUMNS)
    for preset in presets:
        assert "name" in preset
        assert "description" in preset
        assert "features" in preset
        preset_feature_set = set(preset["features"].keys())
        missing_keys = expected_feature_set - preset_feature_set
        assert not missing_keys, f"Preset '{preset['name']}' is missing features: {missing_keys}"


def test_post_run_with_preset_name() -> None:
    """Verify POST /testing/run with preset_name returns 200 and full incident report shape."""
    with TestClient(app) as client:
        response = client.post("/testing/run", json={"preset_name": "DDoS-like"})

    assert response.status_code == 200
    report = response.json()
    expected_top_keys = {
        "request_id",
        "detection",
        "risk_assessment",
        "evidence",
        "context",
        "mitigation",
        "agent_latencies_ms",
    }
    assert expected_top_keys <= report.keys()
    assert report["detection"]["prediction"]
    assert report["risk_assessment"]["risk_label"] in {
        "Low",
        "Medium",
        "High",
        "Critical",
    }
    assert report["agent_latencies_ms"]["total"] > 0.0


def test_post_run_with_custom_features() -> None:
    """Verify POST /testing/run with custom features returns 200 and full incident report."""
    with TestClient(app) as client:
        presets_res = client.get("/testing/presets")
        benign_preset = next(p for p in presets_res.json() if p["name"] == "Benign Traffic")
        response = client.post("/testing/run", json={"features": benign_preset["features"]})

    assert response.status_code == 200
    report = response.json()
    assert "detection" in report
    assert "risk_assessment" in report


def test_post_run_rejects_malformed_features() -> None:
    """Verify POST /testing/run with malformed features returns clean 422 error, not crash."""
    with TestClient(app) as client:
        # Non-numeric feature value
        response = client.post("/testing/run", json={"features": {"Rate": "very fast"}})
        assert response.status_code == 422
        assert "Rate" in response.json()["detail"] or "numeric" in response.json()["detail"].lower()

        # Empty features map
        response_empty = client.post("/testing/run", json={"features": {}})
        assert response_empty.status_code == 422

        # Non-existent preset name
        response_bad_preset = client.post("/testing/run", json={"preset_name": "NonExistentAttack"})
        assert response_bad_preset.status_code == 404
        assert "not found" in response_bad_preset.json()["detail"].lower()
