"""Orchestrator that runs all incident-response agents and builds the report."""

import logging
import time
from typing import Any
from uuid import uuid4

from app.agents import evidence_agent, mitigation_agent, rag_agent, risk_agent

logger = logging.getLogger("kronos")

_DEFAULT_RISK: dict[str, Any] = {
    "risk_score": 0.0,
    "risk_label": "Low",
    "reasoning": "Risk could not be assessed; defaulting to Low.",
}


def _safe_call(
    label: str,
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> tuple[dict[str, Any] | None, str | None, float]:
    """Invoke *func* and return ``(result, error_message, latency_ms)``.

    Exceptions are caught so the pipeline never crashes on a single
    agent failure.
    """
    started_at = time.perf_counter()
    try:
        result = func(*args, **kwargs)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return result, None, latency_ms
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.error("Agent '%s' failed after %.2f ms: %s", label, latency_ms, exc)
        return None, str(exc), latency_ms


def run_pipeline(detection_result: dict[str, Any]) -> dict[str, Any]:
    """Execute all agents and assemble a best-effort incident report.

    The pipeline **always** returns a report — even when one or more
    agents fail.  Failed agents are recorded in the ``errors`` dict and
    their corresponding section falls back to a safe default.

    Parameters
    ----------
    detection_result:
        The dict produced by ``inference.predict()`` enriched with
        ``request_id`` and ``timestamp`` by the endpoint handler.

    Returns
    -------
    dict
        A combined incident report with keys: ``request_id``,
        ``detection``, ``risk_assessment``, ``evidence``, ``context``,
        ``mitigation``, ``agent_latencies_ms``, and ``errors``.
    """
    pipeline_started_at = time.perf_counter()
    request_id: str = detection_result.get("request_id", str(uuid4()))
    errors: dict[str, str] = {}

    prediction: str = detection_result.get("prediction", "Unknown")
    confidence: float = detection_result.get("confidence", 0.0)
    top_features: list[dict[str, Any]] = detection_result.get("top_features", [])

    # ---- RAG Agent ----
    context, rag_err, rag_ms = _safe_call("rag", rag_agent.retrieve_context, prediction)
    if rag_err:
        errors["rag"] = rag_err

    # ---- Risk Agent ----
    risk_assessment, risk_err, risk_ms = _safe_call(
        "risk", risk_agent.assess_risk, prediction, confidence,
    )
    if risk_err:
        errors["risk"] = risk_err
        risk_assessment = dict(_DEFAULT_RISK)

    risk_label: str = risk_assessment.get("risk_label", "Low") if risk_assessment else "Low"

    # ---- Evidence Agent ----
    evidence, ev_err, ev_ms = _safe_call("evidence", evidence_agent.build_evidence, top_features)
    if ev_err:
        errors["evidence"] = ev_err

    # ---- Mitigation Agent ----
    mitigation, mit_err, mit_ms = _safe_call(
        "mitigation",
        mitigation_agent.generate_mitigation,
        prediction,
        risk_label,
        context or {},
    )
    if mit_err:
        errors["mitigation"] = mit_err

    total_ms = round((time.perf_counter() - pipeline_started_at) * 1000, 2)

    report: dict[str, Any] = {
        "request_id": request_id,
        "detection": detection_result,
        "risk_assessment": risk_assessment,
        "evidence": evidence,
        "context": context,
        "mitigation": mitigation,
        "agent_latencies_ms": {
            "rag": rag_ms,
            "risk": risk_ms,
            "evidence": ev_ms,
            "mitigation": mit_ms,
            "total": total_ms,
        },
        "errors": errors,
    }

    if errors:
        logger.warning("Pipeline completed with errors: %s", errors)
    else:
        logger.info("Pipeline completed successfully in %.2f ms", total_ms)

    return report
