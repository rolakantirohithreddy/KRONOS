"""Unit tests for KRONOS incident-analysis agents."""

from typing import Any

import pytest

from app.agents import (
    evidence_agent,
    mitigation_agent,
    orchestrator,
    rag_agent,
    risk_agent,
)
from app.agents.base_agent import BaseAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.mitigation_agent import MitigationAgent
from app.agents.rag_agent import RAGAgent
from app.agents.risk_agent import RiskAgent


# ---- RAG Agent ----


def test_rag_agent_retrieves_known_attack_context() -> None:
    """Retrieve a knowledge-base record for a supported attack type."""
    context = rag_agent.retrieve_context("Mirai")

    assert context["attack_type"] == "Mirai"
    assert context["mitre_technique"]
    assert context["recommended_mitigation"]


def test_rag_agent_returns_generic_unknown_fallback() -> None:
    """Return a manual-review recommendation for an unknown attack type."""
    context = rag_agent.retrieve_context("NovelAttack")

    assert context["attack_type"] == "NovelAttack"
    assert context["mitre_technique"] == "UNKNOWN"
    assert "manual review" in context["description"].lower()


def test_rag_agent_run_with_valid_input() -> None:
    """Verify RAGAgent.run() returns context for a known attack type."""
    agent = RAGAgent()
    result = agent.run({"attack_type": "DDoS"})

    assert result["attack_type"] == "DDoS"
    assert result["mitre_technique"] == "T1498"


def test_rag_agent_execute_catches_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The execute() wrapper returns success=false instead of raising."""
    def broken_run(self: BaseAgent, input_data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("knowledge base corrupt")

    monkeypatch.setattr(RAGAgent, "run", broken_run)
    envelope = RAGAgent().execute({"attack_type": "DDoS"})

    assert envelope["agent"] == "rag"
    assert envelope["success"] is False
    assert envelope["output"] is None
    assert "knowledge base corrupt" in envelope["error"]
    assert isinstance(envelope["latency_ms"], float)


# ---- Risk Agent ----


def test_risk_agent_weights_confidence() -> None:
    """Increase the risk score when confidence increases for the same class."""
    lower_confidence = risk_agent.assess_risk("DDoS", 0.4)
    higher_confidence = risk_agent.assess_risk("DDoS", 0.9)

    assert higher_confidence["risk_score"] > lower_confidence["risk_score"]
    assert higher_confidence["risk_label"] == "Critical"


def test_risk_agent_benign_is_low() -> None:
    """Benign traffic should always score Low regardless of confidence."""
    result = risk_agent.assess_risk("Benign", 0.99)

    assert result["risk_score"] == 0.0
    assert result["risk_label"] == "Low"


def test_risk_agent_run_with_valid_input() -> None:
    """Verify RiskAgent.run() returns expected keys."""
    agent = RiskAgent()
    result = agent.run({"attack_type": "Mirai", "confidence": 0.95})

    assert "risk_score" in result
    assert "risk_label" in result
    assert "reasoning" in result


def test_risk_agent_execute_catches_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The execute() wrapper returns success=false instead of raising."""
    def broken_run(self: BaseAgent, input_data: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("invalid confidence range")

    monkeypatch.setattr(RiskAgent, "run", broken_run)
    envelope = RiskAgent().execute({"attack_type": "DDoS", "confidence": 0.9})

    assert envelope["agent"] == "risk"
    assert envelope["success"] is False
    assert envelope["output"] is None
    assert "invalid confidence range" in envelope["error"]


# ---- Evidence Agent ----


def test_evidence_agent_formats_feature_contribution() -> None:
    """Turn a high-contribution feature into a readable statement."""
    evidence = evidence_agent.build_evidence(
        [
            {
                "feature": "packet_rate",
                "value": 88.2,
                "shap_value": 0.31,
                "direction": "increases risk",
            }
        ]
    )

    assert "High packet rate (88.2) strongly increased" in evidence[
        "evidence_statements"
    ][0]
    assert len(evidence["raw_features"]) == 1


def test_evidence_agent_handles_empty_features() -> None:
    """Return empty evidence collections when no features were provided."""
    evidence = evidence_agent.build_evidence([])

    assert evidence == {"evidence_statements": [], "raw_features": []}


def test_evidence_agent_run_with_valid_input() -> None:
    """Verify EvidenceAgent.run() returns expected keys."""
    agent = EvidenceAgent()
    result = agent.run({"top_features": [
        {"feature": "byte_count", "value": 640.0, "shap_value": -0.15, "direction": "decreases risk"},
    ]})

    assert "evidence_statements" in result
    assert "raw_features" in result
    assert len(result["evidence_statements"]) == 1


def test_evidence_agent_execute_catches_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The execute() wrapper returns success=false instead of raising."""
    def broken_run(self: BaseAgent, input_data: dict[str, Any]) -> dict[str, Any]:
        raise TypeError("unexpected feature format")

    monkeypatch.setattr(EvidenceAgent, "run", broken_run)
    envelope = EvidenceAgent().execute({"top_features": []})

    assert envelope["agent"] == "evidence"
    assert envelope["success"] is False
    assert "unexpected feature format" in envelope["error"]


# ---- Mitigation Agent ----


def test_mitigation_agent_uses_risk_label_as_priority() -> None:
    """Include the risk label and retrieved technique in the recommendation."""
    mitigation = mitigation_agent.generate_mitigation(
        "DDoS",
        "High",
        {
            "mitre_technique": "T1498",
            "recommended_mitigation": "Rate-limit abusive sources.",
        },
    )

    assert mitigation["priority"] == "High"
    assert mitigation["grounded_in"] == "T1498"
    assert "Rate-limit abusive sources" in mitigation["recommended_action"]


def test_mitigation_agent_run_with_valid_input() -> None:
    """Verify MitigationAgent.run() returns expected keys."""
    agent = MitigationAgent()
    result = agent.run({
        "attack_type": "DoS",
        "risk_label": "Critical",
        "context": {"mitre_technique": "T1499", "recommended_mitigation": "Block sources."},
    })

    assert result["priority"] == "Critical"
    assert "IMMEDIATE ACTION REQUIRED" in result["recommended_action"]


def test_mitigation_agent_execute_catches_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The execute() wrapper returns success=false instead of raising."""
    def broken_run(self: BaseAgent, input_data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("LLM service timeout")

    monkeypatch.setattr(MitigationAgent, "run", broken_run)
    envelope = MitigationAgent().execute({"attack_type": "DDoS", "risk_label": "High", "context": {}})

    assert envelope["agent"] == "mitigation"
    assert envelope["success"] is False
    assert "LLM service timeout" in envelope["error"]


# ---- Orchestrator ----


def test_orchestrator_returns_partial_report_when_agent_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record agent errors while allowing remaining pipeline steps to finish."""
    def fail_risk_assessment(attack_type: str, confidence: float) -> dict[str, Any]:
        """Simulate a risk agent failure for pipeline resilience coverage."""
        raise RuntimeError("risk service unavailable")

    monkeypatch.setattr(risk_agent, "assess_risk", fail_risk_assessment)
    report = orchestrator.run_pipeline(
        {
            "prediction": "DDoS",
            "confidence": 0.9,
            "top_features": [],
            "latency_ms": 10.0,
            "request_id": "test-request",
        }
    )

    assert report["errors"]["risk"] == "risk service unavailable"
    assert report["risk_assessment"]["risk_label"] == "Low"
    assert report["context"]["attack_type"] == "DDoS"
    assert report["mitigation"]["priority"] == "Low"
    assert report["agent_latencies_ms"]["total"] >= 0.0


def test_orchestrator_full_success() -> None:
    """Verify a fully successful pipeline has empty errors."""
    report = orchestrator.run_pipeline(
        {
            "prediction": "Mirai",
            "confidence": 0.92,
            "top_features": [
                {"feature": "packet_rate", "value": 120.5, "shap_value": 0.35, "direction": "increases risk"},
            ],
            "latency_ms": 12.0,
            "request_id": "success-test",
        }
    )

    assert report["errors"] == {}
    assert report["risk_assessment"]["risk_label"] == "Critical"
    assert report["context"]["attack_type"] == "Mirai"
    assert report["mitigation"] is not None
    assert report["evidence"]["evidence_statements"]
    assert report["agent_latencies_ms"]["total"] > 0.0