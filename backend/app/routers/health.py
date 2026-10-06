"""Health-check endpoint for the KRONOS backend."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Report service status, current UTC time, and API version."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        version=get_settings().version,
    )