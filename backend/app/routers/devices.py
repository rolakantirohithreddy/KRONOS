"""app/routers/devices.py

Devices router providing real-time LAN device discovery and fingerprinting.
Never returns hardcoded or placeholder device data.
"""

from typing import Any
from fastapi import APIRouter
from app.services import discovery_service

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[dict[str, Any]])
@router.get("/", response_model=list[dict[str, Any]])
def get_devices() -> list[dict[str, Any]]:
    """Return real-time discovered and fingerprinted devices on the local LAN."""
    return discovery_service.discover_devices()
