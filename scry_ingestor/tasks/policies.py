"""Celery retry policy helpers for task execution."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from ..exceptions import CollectionError, ScryIngestorError


DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[ScryIngestorError], ...] = (CollectionError,)


@dataclass(slots=True)
class CeleryRetryPolicy:
    """Encapsulates retry behaviour for Celery task executions."""

    enabled: bool
    max_attempts: int
    backoff_seconds: float
    max_backoff_seconds: float
    retryable_exceptions: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_EXCEPTIONS

    def __post_init__(self) -> None:
        """Validate policy boundaries to avoid misconfiguration."""

        if self.max_attempts < 0:
            raise ValueError("max_attempts must be non-negative")
        if self.backoff_seconds <= 0:
            raise ValueError("backoff_seconds must be greater than zero")
        if self.max_backoff_seconds <= 0:
            raise ValueError("max_backoff_seconds must be greater than zero")
        if self.max_backoff_seconds < self.backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= backoff_seconds")

    def should_retry(self, exc: Exception) -> bool:
        """Return True when the supplied exception is eligible for retry."""

        if not self.enabled:
            return False
        return any(isinstance(exc, error_type) for error_type in self.retryable_exceptions)

    def next_countdown(self, retry_number: int) -> int:
        """Compute the delay before the next retry attempt."""

        exponent = max(retry_number, 0)
        delay = self.backoff_seconds * (2**exponent)
        return int(min(delay, self.max_backoff_seconds))

    def to_dict(self) -> dict[str, object]:
        """Return a serializable representation for logging or persistence."""

        return {
            "enabled": self.enabled,
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds,
            "max_backoff_seconds": self.max_backoff_seconds,
            "retryable_exceptions": [exc.__name__ for exc in self.retryable_exceptions],
        }

    @classmethod
    def with_overrides(
        cls,
        *,
        enabled: bool,
        max_attempts: int,
        backoff_seconds: float,
        max_backoff_seconds: float,
        retryable_exceptions: Sequence[type[Exception]] | None = None,
    ) -> CeleryRetryPolicy:
        """Factory helper that normalizes optional overrides."""

        exceptions: tuple[type[Exception], ...]
        if retryable_exceptions:
            exceptions = tuple(retryable_exceptions)
        else:
            exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

        return cls(
            enabled=enabled,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            retryable_exceptions=exceptions,
        )
