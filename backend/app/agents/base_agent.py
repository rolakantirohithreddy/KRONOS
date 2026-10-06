"""Abstract base class for all incident-response agents."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("kronos")


class BaseAgent(ABC):
    """Base class that provides a consistent execution envelope for agents.

    Every agent inherits from ``BaseAgent`` and implements :meth:`run`.
    Callers should invoke :meth:`execute` instead of ``run`` directly so
    that latency timing, error handling, and response-envelope formatting
    are applied uniformly.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in logs and the orchestrator report."""

    @abstractmethod
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Perform the agent's core logic and return a result dict.

        Subclasses must override this method.  Any exception raised here
        is caught by :meth:`execute` and surfaced in the envelope.
        """

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run the agent and return a consistent result envelope.

        The envelope always contains:
        - ``agent``: the agent's :attr:`name`
        - ``success``: whether :meth:`run` completed without error
        - ``output``: the dict returned by ``run``, or ``None`` on failure
        - ``error``: an error message string, or ``None`` on success
        - ``latency_ms``: wall-clock duration of the ``run`` call
        """
        started_at = time.perf_counter()
        try:
            output = self.run(input_data)
            return {
                "agent": self.name,
                "success": True,
                "output": output,
                "error": None,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            }
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.error(
                "Agent '%s' failed after %.2f ms: %s",
                self.name,
                latency_ms,
                exc,
            )
            return {
                "agent": self.name,
                "success": False,
                "output": None,
                "error": str(exc),
                "latency_ms": latency_ms,
            }
