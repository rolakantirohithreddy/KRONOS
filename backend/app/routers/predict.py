"""Prediction endpoint for network-flow classification."""

import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.models.schemas import NetworkFlowRequest, PredictResponse
from app.services.ml_model import inference
from app.services.logger_service import log_exchange

router = APIRouter(tags=["prediction"])


@router.post("/predict", response_model=PredictResponse)
async def predict_flow(
    sample: NetworkFlowRequest,
    request: Request,
) -> PredictResponse:
    """Classify a network flow and return the result with request metadata."""
    request_id = getattr(request.state, "request_id", str(uuid4()))
    started_at = time.perf_counter()
    detector_result = await run_in_threadpool(inference.predict, sample.root)
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    result = PredictResponse(
        **detector_result,
        latency_ms=detector_result.get("latency_ms", latency_ms),
        request_id=request_id,
        timestamp=datetime.now(timezone.utc),
    )
    log_exchange(
        request_id=request_id,
        endpoint="/predict",
        request_data=sample.root,
        response_data=result.model_dump(mode="json"),
        latency_ms=result.latency_ms,
        status=200,
    )
    return result