"""Integration tests for the multi-agent incident endpoint."""

from typing import Any

import pytest
from starlette.testclient import TestClient

from app.agents import rag_agent
from app.main import app

SAMPLE = {"flow_duration": 123.4, "packet_rate": 88.2, "byte_count": 640.0}


def test_incident_returns_combined_report() -> None:
    """Return detector data and all expected agent report sections."""
    with TestClient(app) as client:
        response = client.post("/incident", json=SAMPLE)

    assert response.status_code == 200
    report = response.json()
    expected_keys = {
        "request_id",
        "detection",
        "risk_assessment",
        "evidence",
        "context",
        "mitigation",
        "agent_latencies_ms",
    }
    assert expected_keys <= report.keys()
    assert report["detection"]["prediction"]
    assert report["risk_assessment"]["risk_label"] in {
        "Low",
        "Medium",
        "High",
        "Critical",
    }
    assert report["mitigation"]["priority"] == report["risk_assessment"][
        "risk_label"
    ]


def test_incident_reports_positive_total_agent_latency() -> None:
    """Include a positive total pipeline duration in the report."""
    with TestClient(app) as client:
        response = client.post("/incident", json=SAMPLE)

    assert response.status_code == 200
    total_latency = response.json()["agent_latencies_ms"]["total"]
    assert isinstance(total_latency, (int, float))
    assert total_latency > 0.0


def test_incident_rejects_malformed_input() -> None:
    """Return a clean 422 response for empty or nonnumeric flow features."""
    with TestClient(app) as client:
        response = client.post("/incident", json={"packet_rate": "fast"})

    assert response.status_code == 422
    assert "packet_rate" in response.json()["detail"]
    assert "must be a number" in response.json()["detail"].lower()


def test_incident_partial_report_on_rag_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return 200 with a partial report when the RAG agent fails."""
    def broken_retrieve(attack_type: str) -> dict[str, Any]:
        raise RuntimeError("knowledge base unavailable")

    monkeypatch.setattr(rag_agent, "retrieve_context", broken_retrieve)
    with TestClient(app) as client:
        response = client.post("/incident", json=SAMPLE)

    assert response.status_code == 200
    report = response.json()
    assert "rag" in report["errors"]
    assert report["context"] is None
    assert report["risk_assessment"] is not None
    assert report["agent_latencies_ms"]["total"] > 0.0