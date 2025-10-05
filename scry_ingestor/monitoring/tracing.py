"""Distributed tracing utilities with correlation ID propagation for Scry_Ingestor.

This module provides context managers and helpers for distributed tracing across
ingestion pipelines, enabling end-to-end request tracking and observability.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from ..utils.logging import setup_logger

logger = setup_logger(__name__, context={"adapter_type": "TracingUtility"})

# Thread-safe storage for correlation IDs across async boundaries
_correlation_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


@dataclass
class TraceSpan:
    """
    Represents a single span in a distributed trace.

    Attributes:
        span_id: Unique identifier for this span
        correlation_id: Correlation ID linking related operations
        operation: Name of the operation being traced
        start_time: Timestamp when span began (seconds since epoch)
        end_time: Timestamp when span ended (optional)
        duration_ms: Duration in milliseconds (computed when span ends)
        metadata: Additional structured context
        parent_span_id: Optional parent span for nested operations
    """

    span_id: str
    correlation_id: str
    operation: str
    start_time: float
    end_time: float | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_span_id: str | None = None

    def finish(self) -> None:
        """Mark the span as complete and calculate duration."""
        if self.end_time is None:
            self.end_time = time.time()
            self.duration_ms = int((self.end_time - self.start_time) * 1000)

    def to_dict(self) -> dict[str, Any]:
        """Serialize span to dictionary for logging/export."""
        return {
            "span_id": self.span_id,
            "correlation_id": self.correlation_id,
            "operation": self.operation,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "parent_span_id": self.parent_span_id,
        }


def get_correlation_id() -> str | None:
    """
    Retrieve the active correlation ID from the current context.

    Returns:
        Active correlation ID or None if not set
    """
    return _correlation_id_context.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID for the current context.

    Args:
        correlation_id: Correlation ID to propagate through trace
    """
    _correlation_id_context.set(correlation_id)


def clear_correlation_id() -> None:
    """Clear the active correlation ID from the current context."""

    _correlation_id_context.set(None)


def generate_correlation_id() -> str:
    """
    Generate a new unique correlation ID.

    Returns:
        UUID4-based correlation ID
    """
    return str(uuid.uuid4())


def ensure_correlation_id(provided_id: str | None = None) -> str:
    """
    Ensure a correlation ID exists, creating one if necessary.

    Args:
        provided_id: Optional correlation ID to use

    Returns:
        The provided ID, existing context ID, or newly generated ID
    """
    if provided_id:
        set_correlation_id(provided_id)
        return provided_id

    existing = get_correlation_id()
    if existing:
        return existing

    new_id = generate_correlation_id()
    set_correlation_id(new_id)
    return new_id


@contextmanager
def trace_span(
    operation: str,
    *,
    correlation_id: str | None = None,
    parent_span_id: str | None = None,
    **metadata: Any,
) -> Iterator[TraceSpan]:
    """
    Context manager for tracing an operation with automatic timing and logging.

    Args:
        operation: Name of the operation being traced
        correlation_id: Optional correlation ID (generated if not provided)
        parent_span_id: Optional parent span ID for nested operations
        **metadata: Additional context to attach to the span

    Yields:
        TraceSpan instance that can be updated during operation

    Example:
        with trace_span("adapter.process", adapter_type="pdf") as span:
            span.metadata["file_size"] = 1024
            # perform operation
    """
    corr_id = ensure_correlation_id(correlation_id)
    span_id = str(uuid.uuid4())

    span = TraceSpan(
        span_id=span_id,
        correlation_id=corr_id,
        operation=operation,
        start_time=time.time(),
        parent_span_id=parent_span_id,
        metadata=metadata,
    )

    logger.debug(
        "Trace span started: %s",
        operation,
        extra={
            "span_id": span_id,
            "correlation_id": corr_id,
            "parent_span_id": parent_span_id,
            "operation": operation,
        },
    )

    try:
        yield span
    finally:
        span.finish()
        logger.debug(
            "Trace span completed: %s (duration: %dms)",
            operation,
            span.duration_ms or 0,
            extra={
                "span_id": span_id,
                "correlation_id": corr_id,
                "duration_ms": span.duration_ms,
                "operation": operation,
                "metadata": span.metadata,
            },
        )


def extract_correlation_id_from_headers(headers: dict[str, str]) -> str | None:
    """
    Extract correlation ID from HTTP headers (case-insensitive).

    Args:
        headers: HTTP request headers

    Returns:
        Correlation ID if found, None otherwise
    """
    header_candidates = ["x-correlation-id", "x-request-id", "correlation-id"]

    headers_lower = {k.lower(): v for k, v in headers.items()}
    for candidate in header_candidates:
        if candidate in headers_lower:
            return headers_lower[candidate]

    return None


def inject_correlation_id_into_headers(
    headers: dict[str, str],
    correlation_id: str | None = None,
) -> dict[str, str]:
    """
    Inject correlation ID into HTTP headers for downstream propagation.

    Args:
        headers: Existing HTTP headers (will not be mutated)
        correlation_id: Correlation ID to inject (uses context if not provided)

    Returns:
        New headers dict with correlation ID added
    """
    corr_id = correlation_id or ensure_correlation_id()
    result = dict(headers)
    result["X-Correlation-ID"] = corr_id
    return result


__all__ = [
    "TraceSpan",
    "get_correlation_id",
    "set_correlation_id",
    "clear_correlation_id",
    "generate_correlation_id",
    "ensure_correlation_id",
    "trace_span",
    "extract_correlation_id_from_headers",
    "inject_correlation_id_into_headers",
]
