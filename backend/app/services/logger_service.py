"""Structured application logging for request and response events."""

import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from app.config import Settings

LOGGER_NAME = "kronos"


class StructuredFormatter(logging.Formatter):
    """Format log records as JSON with stable request metadata fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record and its request context as JSON."""
        payload = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", None),
            "endpoint": getattr(record, "endpoint", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "status": getattr(record, "status", None),
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(settings: Settings) -> None:
    """Configure console and rotating-file handlers for the app logger."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = StructuredFormatter()
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


def log_exchange(
    *,
    request_id: str,
    endpoint: str,
    request_data: dict[str, Any],
    response_data: dict[str, Any],
    latency_ms: float,
    status: int,
) -> None:
    """Log serialized request and response data with inference metadata."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.info(
        "request=%s response=%s",
        json.dumps(request_data, ensure_ascii=True, default=str),
        json.dumps(response_data, ensure_ascii=True, default=str),
        extra={
            "request_id": request_id,
            "endpoint": endpoint,
            "latency_ms": latency_ms,
            "status": status,
        },
    )


def log_request(
    *,
    request_id: str,
    endpoint: str,
    latency_ms: float,
    status: int,
) -> None:
    """Log request completion metadata for every HTTP request."""
    logging.getLogger(LOGGER_NAME).info(
        "request completed",
        extra={
            "request_id": request_id,
            "endpoint": endpoint,
            "latency_ms": latency_ms,
            "status": status,
        },
    )