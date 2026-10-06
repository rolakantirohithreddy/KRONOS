"""FastAPI application entrypoint for the KRONOS backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import logging

from app.config import get_settings
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers import auth, devices, health, incident, monitoring, predict, system, testing
from app.services.logger_service import LOGGER_NAME, configure_logging, log_exchange
from app.models.user import init_db
from fastapi.middleware.cors import CORSMiddleware

settings = get_settings()


from app.services import arp_redirect_service


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize application logging for the lifetime of the API process."""
    configure_logging(settings)
    init_db()
    if settings.resend_api_key and settings.resend_from_email == "onboarding@resend.dev":
        logging.getLogger(LOGGER_NAME).info(
            "Using Resend's shared test domain -- emails will only deliver to <your Resend account email>. "
            "Other users' OTPs will be logged to console instead. To send real emails to any address, verify "
            "your own domain at resend.com/domains and update RESEND_FROM_EMAIL."
        )
    yield
    # Shutdown: restore ARP tables for any actively monitored devices
    arp_redirect_service.stop_all_redirects()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(health.router)
app.include_router(predict.router)
app.include_router(incident.router)
app.include_router(monitoring.router)
app.include_router(system.router)
app.include_router(testing.router)
app.include_router(auth.router)
app.include_router(devices.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Return a short 422 message for malformed request data."""
    messages = []
    for error in exception.errors():
        location = ".".join(
            str(part) for part in error.get("loc", ()) if part != "body"
        )
        field = location or "request body"
        messages.append(f"{field}: {error['msg']}")
    detail = "; ".join(messages) or "Request data is invalid."
    request_body = exception.body
    request_data = (
        request_body if isinstance(request_body, dict) else {"body": request_body}
    )
    started_at = getattr(request.state, "started_at", time.perf_counter())
    log_exchange(
        request_id=getattr(request.state, "request_id", "unknown"),
        endpoint=request.url.path,
        request_data=request_data,
        response_data={"detail": detail},
        latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
        status=422,
    )
    return JSONResponse(status_code=422, content={"detail": detail})