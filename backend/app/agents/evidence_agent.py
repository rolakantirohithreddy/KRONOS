"""Evidence agent that converts SHAP-based feature explanations to prose."""

import logging
from typing import Any

from app.agents.base_agent import BaseAgent

logger = logging.getLogger("kronos")

# Map feature names to human-readable labels for evidence statements.
_FEATURE_LABELS: dict[str, str] = {
    "flow_duration": "flow duration",
    "packet_rate": "packet rate",
    "byte_count": "byte count",
    "dst_port": "destination port",
    "src_port": "source port",
    "protocol": "protocol",
    "flag_count": "flag count",
    "header_length": "header length",
}


def _humanise_feature(feature_name: str) -> str:
    """Return a human-friendly label for a feature name."""
    return _FEATURE_LABELS.get(feature_name, feature_name.replace("_", " "))


def build_evidence(top_features: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert each feature into a natural-language evidence statement.

    Returns empty collections when *top_features* is empty rather than
    crashing, so the pipeline always gets a valid result.
    """
    if not top_features:
        logger.info("No top_features provided; returning empty evidence")
        return {"evidence_statements": [], "raw_features": []}

    statements: list[str] = []
    for feature in top_features:
        feature_name: str = feature.get("feature", "unknown_feature")
        value = feature.get("value", "N/A")
        shap_value: float = feature.get("shap_value", 0.0)
        direction: str = feature.get("direction", "unknown direction")

        magnitude = abs(shap_value)
        strength = "strongly" if magnitude >= 0.25 else "moderately"
        label = _humanise_feature(feature_name)

        if "increases risk" in direction:
            statement = (
                f"High {label} ({value}) {strength} increased "
                f"risk (SHAP {shap_value:+.3f})."
            )
        else:
            statement = (
                f"Low {label} ({value}) {strength} decreased "
                f"risk (SHAP {shap_value:+.3f})."
            )
        statements.append(statement)

    logger.info("Generated %d evidence statement(s)", len(statements))
    return {
        "evidence_statements": statements,
        "raw_features": top_features,
    }


class EvidenceAgent(BaseAgent):
    """Transform detection top_features into human-readable evidence."""

    @property
    def name(self) -> str:  # noqa: D401
        return "evidence"

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to :func:`build_evidence`."""
        return build_evidence(input_data.get("top_features") or [])
