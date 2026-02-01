"""Tests for the Kafka ingestion event publisher."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from scry_ingestor.messaging.publisher import IngestionEventPublisher
from scry_ingestor.schemas.payload import IngestionMetadata, IngestionPayload, ValidationResult
from scry_ingestor.utils.config import get_settings


class _FakeProducer:
    def __init__(self) -> None:
        self.produced: list[tuple[str, bytes]] = []
        self.polled: list[float] = []
        self.closed = False
        self.flush_timeout: float | None = None

    def produce(self, topic: str, value: bytes, on_delivery: Callable | None = None) -> None:
        self.produced.append((topic, value))
        if on_delivery is not None:  # pragma: no cover - normally not invoked in tests
            on_delivery(None, None)

    def poll(self, timeout: float) -> None:
        self.polled.append(timeout)

    def flush(self, timeout: float | None = None) -> None:
        self.flush_timeout = timeout

    def close(self) -> None:
        self.closed = True


class _NoOpAdminClient:
    def __init__(self, *_args, **_kwargs) -> None:  # pragma: no cover - ensure compatibility
        pass

    def list_topics(self, timeout: float) -> None:
        return None


def _build_payload() -> IngestionPayload:
    return IngestionPayload(
        data={"records": 10},
        metadata=IngestionMetadata(
            source_id="source-123",
            adapter_type="json",
            timestamp="2024-01-01T00:00:00Z",
            processing_duration_ms=150,
            processing_mode="local",
            correlation_id="corr-xyz",
        ),
        validation=ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["minor-warning"],
            metrics={"record_count": 10},
        ),
    )


def test_publish_success_uses_serializer_and_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publisher should invoke serializer and send bytes to Kafka."""

    monkeypatch.setenv("SCRY_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    get_settings.cache_clear()

    captured: dict[str, Any] = {}

    def serializer(record: dict[str, Any], _context) -> bytes:
        captured["record"] = record
        return b"encoded-record"

    fake_producer = _FakeProducer()

    publisher = IngestionEventPublisher(
        producer=fake_producer,
        serializer=serializer,
        schema_registry_client=object(),
        topic="test-topic",
    )

    payload = _build_payload()
    publisher.publish_success(payload)

    assert fake_producer.produced == [("test-topic", b"encoded-record")]
    assert captured["record"]["adapter"] == "json"
    assert captured["record"]["validation"]["warning_count"] == 1

    publisher.close()
    assert fake_producer.closed is True
    assert fake_producer.flush_timeout == pytest.approx(
        get_settings().kafka_publish_timeout_seconds
    )

    get_settings.cache_clear()


def test_health_status_reflects_missing_schema_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Health should report degraded when schema registry is unavailable."""

    monkeypatch.setenv("SCRY_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    get_settings.cache_clear()

    fake_producer = _FakeProducer()
    publisher = IngestionEventPublisher(
        producer=fake_producer,
        schema_registry_client=None,
        serializer=None,
        topic="health-topic",
    )

    status = publisher.health_status()
    assert status["status"] == "degraded"

    get_settings.cache_clear()


def test_health_status_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Health should report ok when producer and serializer are available."""

    monkeypatch.setenv("SCRY_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    get_settings.cache_clear()

    fake_producer = _FakeProducer()
    def serializer(record: dict[str, Any], ctx: Any) -> bytes:
        return b"encoded"

    monkeypatch.setattr("scry_ingestor.messaging.publisher.AdminClient", _NoOpAdminClient)

    publisher = IngestionEventPublisher(
        producer=fake_producer,
        serializer=serializer,
        schema_registry_client=object(),
        topic="health-topic",
    )

    status = publisher.health_status()
    assert status["status"] == "ok"

    get_settings.cache_clear()
