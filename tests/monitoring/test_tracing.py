"""Tests for distributed tracing utilities."""

from __future__ import annotations

import time

import pytest

from scry_ingestor.monitoring.tracing import (
    TraceSpan,
    ensure_correlation_id,
    extract_correlation_id_from_headers,
    generate_correlation_id,
    get_correlation_id,
    inject_correlation_id_into_headers,
    set_correlation_id,
    trace_span,
)


class TestCorrelationID:
    """Tests for correlation ID management."""

    def test_generate_correlation_id_returns_uuid(self) -> None:
        """Generated correlation IDs should be valid UUIDs."""
        corr_id = generate_correlation_id()
        assert isinstance(corr_id, str)
        assert len(corr_id) == 36
        assert corr_id.count("-") == 4

    def test_set_and_get_correlation_id(self) -> None:
        """Set and retrieve correlation ID from context."""
        test_id = "test-correlation-123"
        set_correlation_id(test_id)
        assert get_correlation_id() == test_id

    def test_ensure_correlation_id_uses_provided(self) -> None:
        """ensure_correlation_id should use provided ID when given."""
        provided_id = "provided-123"
        result = ensure_correlation_id(provided_id)
        assert result == provided_id
        assert get_correlation_id() == provided_id

    def test_ensure_correlation_id_generates_when_none(self) -> None:
        """ensure_correlation_id should generate new ID when none exists."""
        set_correlation_id("")  # Clear context
        result = ensure_correlation_id()
        assert isinstance(result, str)
        assert len(result) == 36
        assert get_correlation_id() == result


class TestHeaderExtraction:
    """Tests for HTTP header correlation ID extraction."""

    def test_extract_correlation_id_from_standard_header(self) -> None:
        """Extract correlation ID from X-Correlation-ID header."""
        headers = {"X-Correlation-ID": "header-corr-123"}
        result = extract_correlation_id_from_headers(headers)
        assert result == "header-corr-123"

    def test_extract_correlation_id_case_insensitive(self) -> None:
        """Header extraction should be case-insensitive."""
        headers = {"x-correlation-id": "lower-case-123"}
        result = extract_correlation_id_from_headers(headers)
        assert result == "lower-case-123"

    def test_extract_correlation_id_from_request_id(self) -> None:
        """Extract correlation ID from X-Request-ID fallback."""
        headers = {"X-Request-ID": "request-456"}
        result = extract_correlation_id_from_headers(headers)
        assert result == "request-456"

    def test_extract_correlation_id_returns_none_when_absent(self) -> None:
        """Return None when no correlation ID headers present."""
        headers = {"Content-Type": "application/json"}
        result = extract_correlation_id_from_headers(headers)
        assert result is None

    def test_inject_correlation_id_into_headers(self) -> None:
        """Inject correlation ID into headers dict."""
        headers = {"Content-Type": "application/json"}
        result = inject_correlation_id_into_headers(headers, "inject-123")
        assert result["X-Correlation-ID"] == "inject-123"
        assert result["Content-Type"] == "application/json"
        assert "Content-Type" in headers  # Original not mutated

    def test_inject_correlation_id_uses_context(self) -> None:
        """Inject uses context correlation ID when not provided."""
        set_correlation_id("context-789")
        headers = {}
        result = inject_correlation_id_into_headers(headers)
        assert result["X-Correlation-ID"] == "context-789"


class TestTraceSpan:
    """Tests for TraceSpan data structure."""

    def test_trace_span_initialization(self) -> None:
        """TraceSpan should initialize with required fields."""
        span = TraceSpan(
            span_id="span-123",
            correlation_id="corr-456",
            operation="test.operation",
            start_time=time.time(),
        )
        assert span.span_id == "span-123"
        assert span.correlation_id == "corr-456"
        assert span.operation == "test.operation"
        assert span.end_time is None
        assert span.duration_ms is None
        assert span.metadata == {}

    def test_trace_span_finish_calculates_duration(self) -> None:
        """Finishing span should calculate duration in milliseconds."""
        start = time.time()
        span = TraceSpan(
            span_id="span-123",
            correlation_id="corr-456",
            operation="test.operation",
            start_time=start,
        )
        time.sleep(0.1)  # Sleep 100ms
        span.finish()

        assert span.end_time is not None
        assert span.end_time > start
        assert span.duration_ms is not None
        assert span.duration_ms >= 100

    def test_trace_span_to_dict(self) -> None:
        """TraceSpan should serialize to dictionary."""
        span = TraceSpan(
            span_id="span-123",
            correlation_id="corr-456",
            operation="test.operation",
            start_time=1234567890.0,
            metadata={"key": "value"},
        )
        span.finish()

        result = span.to_dict()
        assert result["span_id"] == "span-123"
        assert result["correlation_id"] == "corr-456"
        assert result["operation"] == "test.operation"
        assert result["start_time"] == 1234567890.0
        assert result["end_time"] is not None
        assert result["duration_ms"] is not None
        assert result["metadata"] == {"key": "value"}


class TestTraceSpanContextManager:
    """Tests for trace_span context manager."""

    def test_trace_span_context_manager(self) -> None:
        """trace_span should create and finish span automatically."""
        with trace_span("test.operation", correlation_id="test-corr") as span:
            assert isinstance(span, TraceSpan)
            assert span.operation == "test.operation"
            assert span.correlation_id == "test-corr"
            assert span.end_time is None

        assert span.end_time is not None
        assert span.duration_ms is not None

    def test_trace_span_generates_correlation_id(self) -> None:
        """trace_span should generate correlation ID when not provided."""
        with trace_span("test.operation") as span:
            assert span.correlation_id is not None
            assert len(span.correlation_id) == 36

    def test_trace_span_accepts_metadata(self) -> None:
        """trace_span should accept metadata kwargs."""
        with trace_span("test.operation", adapter="pdf", size=1024) as span:
            assert span.metadata["adapter"] == "pdf"
            assert span.metadata["size"] == 1024

    def test_trace_span_updates_metadata_during_operation(self) -> None:
        """Span metadata can be updated during operation."""
        with trace_span("test.operation") as span:
            span.metadata["status"] = "processing"
            span.metadata["items_processed"] = 42

        assert span.metadata["status"] == "processing"
        assert span.metadata["items_processed"] == 42

    def test_trace_span_finishes_on_exception(self) -> None:
        """Span should finish even if exception occurs."""
        span = None
        with pytest.raises(ValueError):
            with trace_span("test.operation") as span:
                raise ValueError("Test error")

        assert span is not None
        assert span.end_time is not None
        assert span.duration_ms is not None

    def test_trace_span_parent_child_relationship(self) -> None:
        """Trace spans should support parent-child relationships."""
        with trace_span("parent.operation") as parent:
            parent_span_id = parent.span_id

            with trace_span(
                "child.operation",
                parent_span_id=parent_span_id,
            ) as child:
                assert child.parent_span_id == parent_span_id
                assert child.correlation_id == parent.correlation_id

        assert parent.end_time is not None
        assert child.end_time is not None
