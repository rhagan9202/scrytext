"""Tests for enhanced Prometheus metrics."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from scry_ingestor.monitoring.metrics import (
    decrement_active_requests,
    increment_active_requests,
    observe_payload_size,
    observe_processing_duration,
    observe_trace_span_duration,
    record_ingestion_attempt,
    record_ingestion_error,
    record_sla_violation,
    record_trace_span_created,
    record_validation_error,
    record_validation_warning,
)


def _get_metric_value(metric_name: str, labels: dict[str, str] | None = None) -> float:
    """Helper to retrieve current metric value from registry."""
    labels = labels or {}
    value = REGISTRY.get_sample_value(metric_name, labels)
    return float(value) if value is not None else 0.0


class TestCoreMetrics:
    """Tests for existing core metrics."""

    def test_record_ingestion_attempt_increments_counter(self) -> None:
        """Recording ingestion attempt should increment counter."""
        before = _get_metric_value(
            "ingestion_attempts_total",
            {"adapter": "test-adapter", "status": "success"},
        )
        record_ingestion_attempt("test-adapter", "success")
        after = _get_metric_value(
            "ingestion_attempts_total",
            {"adapter": "test-adapter", "status": "success"},
        )
        assert after == pytest.approx(before + 1)

    def test_record_ingestion_error_increments_counter(self) -> None:
        """Recording ingestion error should increment counter."""
        before = _get_metric_value("ingestion_errors_total", {"error_type": "TestError"})
        record_ingestion_error("TestError")
        after = _get_metric_value("ingestion_errors_total", {"error_type": "TestError"})
        assert after == pytest.approx(before + 1)

    def test_observe_processing_duration_updates_histogram(self) -> None:
        """Observing processing duration should update histogram."""
        before_count = _get_metric_value("processing_duration_seconds_count")
        observe_processing_duration(2.5)
        after_count = _get_metric_value("processing_duration_seconds_count")
        assert after_count == pytest.approx(before_count + 1)

    def test_observe_processing_duration_handles_negative(self) -> None:
        """Negative duration should be clamped to zero."""
        before_count = _get_metric_value("processing_duration_seconds_count")
        observe_processing_duration(-1.0)
        after_count = _get_metric_value("processing_duration_seconds_count")
        assert after_count == pytest.approx(before_count + 1)


class TestSLAMetrics:
    """Tests for SLA monitoring metrics."""

    def test_record_sla_violation_default_severity(self) -> None:
        """SLA violation should default to warning severity."""
        before = _get_metric_value(
            "ingestion_sla_violations_total",
            {"adapter": "test-adapter", "severity": "warning"},
        )
        record_sla_violation("test-adapter")
        after = _get_metric_value(
            "ingestion_sla_violations_total",
            {"adapter": "test-adapter", "severity": "warning"},
        )
        assert after == pytest.approx(before + 1)

    def test_record_sla_violation_custom_severity(self) -> None:
        """SLA violation should support custom severity."""
        before = _get_metric_value(
            "ingestion_sla_violations_total",
            {"adapter": "test-adapter", "severity": "critical"},
        )
        record_sla_violation("test-adapter", severity="critical")
        after = _get_metric_value(
            "ingestion_sla_violations_total",
            {"adapter": "test-adapter", "severity": "critical"},
        )
        assert after == pytest.approx(before + 1)

    def test_increment_active_requests(self) -> None:
        """Incrementing active requests should update gauge."""
        before = _get_metric_value("ingestion_active_requests", {"adapter": "test-adapter"})
        increment_active_requests("test-adapter")
        after = _get_metric_value("ingestion_active_requests", {"adapter": "test-adapter"})
        assert after == pytest.approx(before + 1)

    def test_decrement_active_requests(self) -> None:
        """Decrementing active requests should update gauge."""
        increment_active_requests("test-adapter")
        before = _get_metric_value("ingestion_active_requests", {"adapter": "test-adapter"})
        decrement_active_requests("test-adapter")
        after = _get_metric_value("ingestion_active_requests", {"adapter": "test-adapter"})
        assert after == pytest.approx(before - 1)


class TestPayloadMetrics:
    """Tests for payload size tracking."""

    def test_observe_payload_size_updates_histogram(self) -> None:
        """Observing payload size should update histogram."""
        before_count = _get_metric_value(
            "ingestion_payload_size_bytes_count",
            {"adapter": "test-adapter"},
        )
        observe_payload_size("test-adapter", 1024)
        after_count = _get_metric_value(
            "ingestion_payload_size_bytes_count",
            {"adapter": "test-adapter"},
        )
        assert after_count == pytest.approx(before_count + 1)

    def test_observe_payload_size_handles_negative(self) -> None:
        """Negative payload size should be clamped to zero."""
        before_count = _get_metric_value(
            "ingestion_payload_size_bytes_count",
            {"adapter": "test-adapter"},
        )
        observe_payload_size("test-adapter", -100)
        after_count = _get_metric_value(
            "ingestion_payload_size_bytes_count",
            {"adapter": "test-adapter"},
        )
        assert after_count == pytest.approx(before_count + 1)


class TestTracingMetrics:
    """Tests for distributed tracing metrics."""

    def test_record_trace_span_created(self) -> None:
        """Recording trace span creation should increment counter."""
        before = _get_metric_value(
            "trace_spans_created_total",
            {"operation": "test.operation"},
        )
        record_trace_span_created("test.operation")
        after = _get_metric_value(
            "trace_spans_created_total",
            {"operation": "test.operation"},
        )
        assert after == pytest.approx(before + 1)

    def test_observe_trace_span_duration(self) -> None:
        """Observing trace span duration should update histogram."""
        before_count = _get_metric_value(
            "trace_span_duration_seconds_count",
            {"operation": "test.operation"},
        )
        observe_trace_span_duration("test.operation", 0.123)
        after_count = _get_metric_value(
            "trace_span_duration_seconds_count",
            {"operation": "test.operation"},
        )
        assert after_count == pytest.approx(before_count + 1)

    def test_observe_trace_span_duration_handles_negative(self) -> None:
        """Negative span duration should be clamped to zero."""
        before_count = _get_metric_value(
            "trace_span_duration_seconds_count",
            {"operation": "test.operation"},
        )
        observe_trace_span_duration("test.operation", -0.5)
        after_count = _get_metric_value(
            "trace_span_duration_seconds_count",
            {"operation": "test.operation"},
        )
        assert after_count == pytest.approx(before_count + 1)


class TestValidationMetrics:
    """Tests for validation metrics."""

    def test_record_validation_error_default_category(self) -> None:
        """Validation error should default to general category."""
        before = _get_metric_value(
            "validation_errors_total",
            {"adapter": "test-adapter", "error_category": "general"},
        )
        record_validation_error("test-adapter")
        after = _get_metric_value(
            "validation_errors_total",
            {"adapter": "test-adapter", "error_category": "general"},
        )
        assert after == pytest.approx(before + 1)

    def test_record_validation_error_custom_category(self) -> None:
        """Validation error should support custom category."""
        before = _get_metric_value(
            "validation_errors_total",
            {"adapter": "test-adapter", "error_category": "schema"},
        )
        record_validation_error("test-adapter", error_category="schema")
        after = _get_metric_value(
            "validation_errors_total",
            {"adapter": "test-adapter", "error_category": "schema"},
        )
        assert after == pytest.approx(before + 1)

    def test_record_validation_warning_default_category(self) -> None:
        """Validation warning should default to general category."""
        before = _get_metric_value(
            "validation_warnings_total",
            {"adapter": "test-adapter", "warning_category": "general"},
        )
        record_validation_warning("test-adapter")
        after = _get_metric_value(
            "validation_warnings_total",
            {"adapter": "test-adapter", "warning_category": "general"},
        )
        assert after == pytest.approx(before + 1)

    def test_record_validation_warning_custom_category(self) -> None:
        """Validation warning should support custom category."""
        before = _get_metric_value(
            "validation_warnings_total",
            {"adapter": "test-adapter", "warning_category": "format"},
        )
        record_validation_warning("test-adapter", warning_category="format")
        after = _get_metric_value(
            "validation_warnings_total",
            {"adapter": "test-adapter", "warning_category": "format"},
        )
        assert after == pytest.approx(before + 1)
