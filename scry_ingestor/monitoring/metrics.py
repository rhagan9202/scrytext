"""Prometheus metrics definitions for Scry_Ingestor."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

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


def record_ingestion_attempt(adapter: str, status: str) -> None:
    """Increment the ingestion attempts counter with the supplied labels."""

    INGESTION_ATTEMPTS.labels(adapter=adapter, status=status).inc()


def record_ingestion_error(error_type: str) -> None:
    """Increment the ingestion errors counter for the provided error type."""

    INGESTION_ERRORS.labels(error_type=error_type).inc()


def observe_processing_duration(duration_seconds: float) -> None:
    """Record the ingestion processing duration in seconds."""

    PROCESSING_DURATION.observe(max(duration_seconds, 0.0))
