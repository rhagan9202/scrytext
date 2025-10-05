"""Prometheus metrics definitions for Scry_Ingestor."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

INGESTION_ATTEMPTS = Counter(
    "ingestion_attempts_total",
    "Total ingestion attempts by adapter and status.",
    labelnames=("adapter", "status"),
)

INGESTION_ERRORS = Counter(
    "ingestion_errors_total",
    "Total ingestion errors grouped by error type.",
    labelnames=("error_type",),
)

PROCESSING_DURATION = Histogram(
    "processing_duration_seconds",
    "Distribution of ingestion processing durations in seconds.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

# SLA monitoring metrics
INGESTION_SLA_VIOLATIONS = Counter(
    "ingestion_sla_violations_total",
    "Total number of ingestion operations that exceeded SLA thresholds.",
    labelnames=("adapter", "severity"),
)

INGESTION_ACTIVE_REQUESTS = Gauge(
    "ingestion_active_requests",
    "Number of currently active ingestion requests.",
    labelnames=("adapter",),
)

INGESTION_PAYLOAD_SIZE_BYTES = Histogram(
    "ingestion_payload_size_bytes",
    "Distribution of ingestion payload sizes in bytes.",
    labelnames=("adapter",),
    buckets=(1024, 10240, 102400, 1024000, 10240000, 104857600),
)

# Distributed tracing metrics
TRACE_SPANS_CREATED = Counter(
    "trace_spans_created_total",
    "Total number of trace spans created.",
    labelnames=("operation",),
)

TRACE_SPAN_DURATION = Histogram(
    "trace_span_duration_seconds",
    "Distribution of trace span durations in seconds.",
    labelnames=("operation",),
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 10),
)

# Validation metrics
VALIDATION_ERRORS = Counter(
    "validation_errors_total",
    "Total validation errors encountered during ingestion.",
    labelnames=("adapter", "error_category"),
)

VALIDATION_WARNINGS = Counter(
    "validation_warnings_total",
    "Total validation warnings encountered during ingestion.",
    labelnames=("adapter", "warning_category"),
)


def record_ingestion_attempt(adapter: str, status: str) -> None:
    """Increment the ingestion attempts counter with the supplied labels."""

    INGESTION_ATTEMPTS.labels(adapter=adapter, status=status).inc()


def record_ingestion_error(error_type: str) -> None:
    """Increment the ingestion errors counter for the provided error type."""

    INGESTION_ERRORS.labels(error_type=error_type).inc()


def observe_processing_duration(duration_seconds: float) -> None:
    """Record the ingestion processing duration in seconds."""

    PROCESSING_DURATION.observe(max(duration_seconds, 0.0))


def record_sla_violation(adapter: str, severity: str = "warning") -> None:
    """
    Record an SLA threshold violation for an ingestion operation.

    Args:
        adapter: Adapter type that violated SLA
        severity: Severity level (warning, critical)
    """
    INGESTION_SLA_VIOLATIONS.labels(adapter=adapter, severity=severity).inc()


def increment_active_requests(adapter: str) -> None:
    """Increment the count of active ingestion requests for an adapter."""
    INGESTION_ACTIVE_REQUESTS.labels(adapter=adapter).inc()


def decrement_active_requests(adapter: str) -> None:
    """Decrement the count of active ingestion requests for an adapter."""
    INGESTION_ACTIVE_REQUESTS.labels(adapter=adapter).dec()


def observe_payload_size(adapter: str, size_bytes: int) -> None:
    """
    Record the size of an ingestion payload.

    Args:
        adapter: Adapter type
        size_bytes: Payload size in bytes
    """
    INGESTION_PAYLOAD_SIZE_BYTES.labels(adapter=adapter).observe(max(size_bytes, 0))


def record_trace_span_created(operation: str) -> None:
    """
    Record the creation of a trace span.

    Args:
        operation: Operation name being traced
    """
    TRACE_SPANS_CREATED.labels(operation=operation).inc()


def observe_trace_span_duration(operation: str, duration_seconds: float) -> None:
    """
    Record the duration of a trace span.

    Args:
        operation: Operation name that was traced
        duration_seconds: Duration in seconds
    """
    TRACE_SPAN_DURATION.labels(operation=operation).observe(max(duration_seconds, 0.0))


def record_validation_error(adapter: str, error_category: str = "general") -> None:
    """
    Record a validation error during ingestion.

    Args:
        adapter: Adapter type
        error_category: Category of validation error
    """
    VALIDATION_ERRORS.labels(adapter=adapter, error_category=error_category).inc()


def record_validation_warning(adapter: str, warning_category: str = "general") -> None:
    """
    Record a validation warning during ingestion.

    Args:
        adapter: Adapter type
        warning_category: Category of validation warning
    """
    VALIDATION_WARNINGS.labels(adapter=adapter, warning_category=warning_category).inc()

