"""Mitigation agent that generates a recommended incident response.

This implementation is rule-based: it combines the RAG context's
``recommended_mitigation`` with urgency framing derived from the risk
label.  It will later call an LLM grounded in the RAG context to
produce richer, situation-specific guidance.  The input/output contract
is intentionally stable so nothing downstream changes when the LLM
backend is integrated.
"""

import logging
from typing import Any

from app.agents.base_agent import BaseAgent

logger = logging.getLogger("kronos")

_URGENCY_PREFIX: dict[str, str] = {
    "Critical": "IMMEDIATE ACTION REQUIRED — ",
    "High": "Urgent — ",
    "Medium": "Recommended — ",
    "Low": "Advisory — ",
}


def generate_mitigation(
    attack_type: str,
    risk_label: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Combine RAG context with risk-label urgency framing.

    Parameters
    ----------
    attack_type:
        The predicted attack label.
    risk_label:
        Low / Medium / High / Critical.
    context:
        Dict from the RAG agent with at least ``recommended_mitigation``
        and ``mitre_technique``.
    """
    base_mitigation: str = context.get(
        "recommended_mitigation",
        "No specific mitigation guidance is available. "
        "Isolate the affected device and escalate to the SOC.",
    )
    urgency = _URGENCY_PREFIX.get(risk_label, "")
    recommended_action = (
        f"{urgency}{base_mitigation} "
        f"(Attack type: {attack_type}, Risk: {risk_label})"
    )

    mitre_technique: str | None = context.get("mitre_technique")
    logger.info(
        "Mitigation generated for '%s' (risk=%s, technique=%s)",
        attack_type,
        risk_label,
        mitre_technique,
    )
    return {
        "recommended_action": recommended_action,
        "priority": risk_label,
        "grounded_in": mitre_technique,
    }


class MitigationAgent(BaseAgent):
    """Generate a recommended response action for an incident."""

    @property
    def name(self) -> str:  # noqa: D401
        return "mitigation"

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to :func:`generate_mitigation`."""
        return generate_mitigation(
            input_data.get("attack_type", "Unknown"),
            input_data.get("risk_label", "Medium"),
            input_data.get("context") or {},
        )
