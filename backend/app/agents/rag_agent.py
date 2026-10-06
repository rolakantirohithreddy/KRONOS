"""RAG agent that retrieves attack context from a local knowledge base.

This implementation performs exact-match lookup against a JSON knowledge
base loaded from disk.  It will later be replaced by a Chroma vector DB
indexed with real MITRE ATT&CK STIX data.  The input/output contract
(``{"attack_type": str}`` → context dict) is intentionally stable so
nothing downstream changes when the retrieval backend is swapped.
"""

import json
import logging
from typing import Any

from app.agents.base_agent import BaseAgent
from app.config import get_settings

logger = logging.getLogger("kronos")

_FALLBACK_ENTRY: dict[str, str] = {
    "attack_type": "Unknown",
    "mitre_technique": "UNKNOWN",
    "technique_name": "Unrecognized Activity",
    "description": (
        "The detected activity does not match any known attack signature in "
        "the current knowledge base. Manual review is recommended."
    ),
    "typical_impact": (
        "Impact cannot be determined automatically; treat as potentially "
        "malicious until reviewed by an analyst."
    ),
    "recommended_mitigation": (
        "Isolate the affected device, capture traffic for forensic review, "
        "and escalate to the security operations team."
    ),
}


def _load_knowledge_base() -> list[dict[str, str]]:
    """Read the JSON knowledge base from the configured path."""
    kb_path = get_settings().knowledge_base_path
    with open(kb_path, encoding="utf-8") as fh:
        data: list[dict[str, str]] = json.load(fh)
    return data


def retrieve_context(attack_type: str) -> dict[str, Any]:
    """Look up *attack_type* in the knowledge base.

    Returns the matching entry or a generic fallback when the attack
    type is not recognised — never raises on unknown input.
    """
    entries = _load_knowledge_base()
    for entry in entries:
        if entry.get("attack_type", "").lower() == attack_type.lower():
            logger.info("RAG matched knowledge-base entry for '%s'", attack_type)
            return dict(entry)

    logger.warning(
        "No knowledge-base match for '%s'; returning fallback", attack_type,
    )
    return {**_FALLBACK_ENTRY, "attack_type": attack_type}


class RAGAgent(BaseAgent):
    """Retrieve contextual attack information from the local knowledge base."""

    @property
    def name(self) -> str:  # noqa: D401
        return "rag"

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to :func:`retrieve_context`."""
        return retrieve_context(input_data.get("attack_type", ""))
