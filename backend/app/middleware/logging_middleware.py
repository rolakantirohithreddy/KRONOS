"""HTTP middleware for request IDs and automatic latency logging."""

import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.services.logger_service import log_request


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and log completion metadata for each request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Measure request duration and log its endpoint and final status."""
        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        request.state.started_at = started_at

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = (time.perf_counter() - started_at) * 1000
            log_request(
                request_id=request_id,
                endpoint=request.url.path,
                latency_ms=round(latency_ms, 2),
                status=500,
            )
            raise

        latency_ms = (time.perf_counter() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        log_request(
            request_id=request_id,
            endpoint=request.url.path,
            latency_ms=round(latency_ms, 2),
            status=response.status_code,
        )
        return response