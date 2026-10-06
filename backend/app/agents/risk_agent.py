"""Risk-scoring agent that evaluates severity from attack type and confidence."""

import logging
from typing import Any

from app.agents.base_agent import BaseAgent

logger = logging.getLogger("kronos")

# Severity weight per attack type (0.0 – 1.0).
_SEVERITY_WEIGHTS: dict[str, float] = {
    "Benign": 0.0,
    "Recon": 0.4,
    "BruteForce": 0.5,
    "Spoofing": 0.6,
    "Web-based": 0.7,
    "DoS": 0.8,
    "DDoS": 0.9,
    "Mirai": 0.95,
}

_DEFAULT_WEIGHT: float = 0.5


def _risk_label(score: float) -> str:
    """Map a numeric risk score to a human-readable label."""
    if score < 0.25:
        return "Low"
    if score < 0.50:
        return "Medium"
    if score < 0.75:
        return "High"
    return "Critical"


def assess_risk(attack_type: str, confidence: float) -> dict[str, Any]:
    """Compute risk score from *attack_type* and *confidence*.

    ``risk_score = severity_weight * confidence``, mapped to one of
    Low / Medium / High / Critical.
    """
    weight = _SEVERITY_WEIGHTS.get(attack_type, _DEFAULT_WEIGHT)
    risk_score = round(weight * confidence, 4)
    label = _risk_label(risk_score)

    reasoning = (
        f"Attack type '{attack_type}' carries severity weight {weight}. "
        f"Combined with detector confidence {confidence:.2f}, the "
        f"computed risk score is {risk_score:.4f} ({label})."
    )
    logger.info("Risk assessment: %s (score=%.4f)", label, risk_score)
    return {
        "risk_score": risk_score,
        "risk_label": label,
        "reasoning": reasoning,
    }


class RiskAgent(BaseAgent):
    """Score incident severity using a weighted confidence formula."""

    @property
    def name(self) -> str:  # noqa: D401
        return "risk"

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to :func:`assess_risk`."""
        return assess_risk(
            input_data.get("attack_type", "Unknown"),
            float(input_data.get("confidence", 0.0)),
        )
