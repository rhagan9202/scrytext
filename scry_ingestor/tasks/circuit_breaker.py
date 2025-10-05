"""Circuit breaker implementation for Celery ingestion tasks."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock

from ..exceptions import CircuitBreakerOpenError
from ..utils.config import get_settings
from ..utils.logging import setup_logger

logger = setup_logger(__name__, context={"adapter_type": "CeleryCircuit"})


@dataclass(slots=True)
class CircuitState:
    """Tracks failure history for a single adapter."""

    failure_timestamps: deque[datetime] = field(default_factory=deque)
    open_until: datetime | None = None


class CircuitBreakerRegistry:
    """In-memory circuit breaker registry keyed by adapter name."""

    def __init__(self) -> None:
        self._states: dict[str, CircuitState] = defaultdict(CircuitState)
        self._lock = Lock()

    def ensure_available(self, adapter_type: str) -> None:
        """Raise when the adapter circuit is currently open."""

        now = datetime.now(timezone.utc)
        with self._lock:
            state = self._states[adapter_type]
            if state.open_until is None:
                return
            if state.open_until <= now:
                state.open_until = None
                state.failure_timestamps.clear()
                return
            raise CircuitBreakerOpenError(adapter_type=adapter_type, reopen_at=state.open_until)

    def record_failure(self, adapter_type: str) -> None:
        """Record a failure occurrence and open the circuit when threshold exceeded."""

        settings = get_settings()
        threshold = settings.celery_failure_threshold
        window = timedelta(seconds=settings.celery_failure_window_seconds)
        cooldown = timedelta(seconds=settings.celery_circuit_reset_seconds)

        now = datetime.now(timezone.utc)
        with self._lock:
            state = self._states[adapter_type]
            state.failure_timestamps.append(now)

            while state.failure_timestamps and now - state.failure_timestamps[0] > window:
                state.failure_timestamps.popleft()

            if len(state.failure_timestamps) >= threshold:
                state.open_until = now + cooldown
                logger.error(
                    "Circuit breaker opened for adapter after %s failures",
                    len(state.failure_timestamps),
                    extra={
                        "adapter_type": adapter_type,
                        "status": "error",
                        "failure_count": len(state.failure_timestamps),
                        "open_until": state.open_until.isoformat() if state.open_until else "-",
                    },
                )

    def record_success(self, adapter_type: str) -> None:
        """Reset the circuit after a successful ingestion."""

        with self._lock:
            state = self._states.get(adapter_type)
            if state is None:
                return
            state.failure_timestamps.clear()
            state.open_until = None

    def reset(self) -> None:
        """Reset all circuits (primarily used in testing)."""

        with self._lock:
            self._states.clear()


_circuit_breaker = CircuitBreakerRegistry()


def get_circuit_breaker() -> CircuitBreakerRegistry:
    """Return the global circuit breaker registry instance."""

    return _circuit_breaker
