"""Custom exceptions for Scry_Ingestor."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:  # pragma: no cover - type checking only
    from scry_ingestor.tasks.error_handling import TaskErrorReport
    from scry_ingestor.tasks.policies import CeleryRetryPolicy


class ScryIngestorError(Exception):
    """Base exception for all Scry_Ingestor errors."""

    pass


class CollectionError(ScryIngestorError):
    """Raised when data collection from source fails."""

    pass


class ValidationError(ScryIngestorError):
    """Raised when data validation fails."""

    pass


class TransformationError(ScryIngestorError):
    """Raised when data transformation fails."""

    pass


class ConfigurationError(ScryIngestorError):
    """Raised when configuration is invalid or missing."""

    pass


class AdapterNotFoundError(ScryIngestorError):
    """Raised when requested adapter is not registered."""

    pass


class AuthenticationError(ScryIngestorError):
    """Raised when API authentication fails."""

    pass


class CircuitBreakerOpenError(ScryIngestorError):
    """Raised when an adapter's circuit breaker is open due to recent failures."""

    def __init__(self, adapter_type: str, reopen_at: datetime | None = None) -> None:
        message = (
            f"Circuit breaker open for adapter '{adapter_type}'. "
            "New tasks are temporarily rejected."
        )
        if reopen_at is not None:
            message = f"{message} Retry after {reopen_at.isoformat()}"
        super().__init__(message)
        self.adapter_type = adapter_type
        self.reopen_at = reopen_at


class TaskExecutionError(ScryIngestorError):
    """Raised when a Celery task execution fails after structured reporting."""

    def __init__(
        self,
    report: TaskErrorReport,
        *,
        original_error: Exception | None = None,
    retry_policy: CeleryRetryPolicy | None = None,
    ) -> None:
        super().__init__(report.message)
        self.report = report
        self.original_error = original_error
        self.retry_policy = retry_policy

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the task error for logging/tests."""

        return {
            "message": self.report.message,
            "error_type": self.report.error_type,
            "classification": self.report.classification,
            "retryable": self.report.retryable,
        }

