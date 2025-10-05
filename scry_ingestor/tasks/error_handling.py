"""Structured error handling utilities for Celery ingestion tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..exceptions import (
    AdapterNotFoundError,
    AuthenticationError,
    CircuitBreakerOpenError,
    CollectionError,
    ConfigurationError,
    ScryIngestorError,
    TransformationError,
    ValidationError,
)


@dataclass(slots=True)
class TaskErrorReport:
    """Structured payload describing a failed Celery ingestion attempt."""

    adapter_type: str
    source_id: str
    correlation_id: str | None
    error_type: str
    message: str
    classification: str
    retryable: bool
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable dictionary representation of the error report."""

        payload: dict[str, Any] = {
            "adapter_type": self.adapter_type,
            "source_id": self.source_id,
            "correlation_id": self.correlation_id,
            "error_type": self.error_type,
            "message": self.message,
            "classification": self.classification,
            "retryable": self.retryable,
            "timestamp": self.timestamp,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def build_error_report(
    exc: Exception,
    *,
    adapter_type: str,
    source_id: str,
    correlation_id: str | None,
    retryable_override: bool | None = None,
    extra_details: dict[str, Any] | None = None,
) -> TaskErrorReport:
    """Construct a :class:`TaskErrorReport` describing the supplied exception."""

    classification, default_retryable = _classify_exception(exc)
    retryable = retryable_override if retryable_override is not None else default_retryable

    timestamp = datetime.now(timezone.utc).isoformat()
    details: dict[str, Any] = {
        "args": [repr(arg) for arg in getattr(exc, "args", ())],
        "exception_module": exc.__class__.__module__,
    }
    if extra_details:
        details.update(extra_details)

    message = str(exc) if str(exc) else exc.__class__.__name__

    return TaskErrorReport(
        adapter_type=adapter_type,
        source_id=source_id,
        correlation_id=correlation_id,
        error_type=exc.__class__.__name__,
        message=message,
        classification=classification,
        retryable=retryable,
        timestamp=timestamp,
        details=details,
    )


def build_failure_summary(report: TaskErrorReport) -> dict[str, Any]:
    """Generate a validation summary payload compatible with persistence schema."""

    return {
        "is_valid": False,
        "error_count": 1,
        "warning_count": 0,
        "metrics": {},
        "errors": [report.message],
        "warnings": [],
    }


def _classify_exception(exc: Exception) -> tuple[str, bool]:
    """Return a tuple of (classification, retryable) for a given exception."""

    if isinstance(exc, CircuitBreakerOpenError):
        return "circuit_open", False
    if isinstance(exc, AdapterNotFoundError):
        return "configuration", False
    if isinstance(exc, ConfigurationError):
        return "configuration", False
    if isinstance(exc, AuthenticationError):
        return "authentication", False
    if isinstance(exc, ValidationError):
        return "validation", False
    if isinstance(exc, TransformationError):
        return "transformation", False
    if isinstance(exc, CollectionError):
        # Adapters implement their own retransmission strategies; avoid Celery-level retries.
        return "collection", False
    if isinstance(exc, ScryIngestorError):
        return "application", False
    return "unexpected", False
