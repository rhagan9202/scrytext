"""Tests for the Kafka ingestion event publisher."""

from __future__ import annotations

import io
from typing import Any, cast

from fastavro import schemaless_reader

from scry_ingestor.messaging.publisher import IngestionEventPublisher
from scry_ingestor.messaging.schema import INGESTION_EVENT_SCHEMA
from scry_ingestor.schemas.payload import IngestionMetadata, IngestionPayload, ValidationResult
from scry_ingestor.utils.config import get_settings


class _FakeFuture:
    def get(self, timeout: float | None = None):  # pragma: no cover - behaves like Kafka future
        return None


class _FakeProducer:
    def __init__(self, bootstrap_servers):
        self.bootstrap_servers = bootstrap_servers
        self.sent: list[tuple[str, bytes]] = []

    def send(self, topic: str, value: bytes):  # type: ignore[override]
        self.sent.append((topic, value))
        return _FakeFuture()

    def flush(self) -> None:  # pragma: no cover - no-op for fake producer
        return None

    def close(self) -> None:  # pragma: no cover - no-op for fake producer
        return None


def test_publish_success_serializes_avro(monkeypatch):
    """Publisher should serialize ingestion payloads to Avro and send them to Kafka."""

    monkeypatch.setenv("SCRY_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    get_settings.cache_clear()

    monkeypatch.setattr("scry_ingestor.messaging.publisher.KafkaProducer", _FakeProducer)

    publisher = IngestionEventPublisher()

    payload = IngestionPayload(
        data={"records": 10},
        metadata=IngestionMetadata(
            source_id="source-123",
            adapter_type="JSONAdapter",
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

    publisher.publish_success(payload)

    assert publisher._producer is not None  # type: ignore[attr-defined]
    assert len(publisher._producer.sent) == 1  # type: ignore[attr-defined]

    topic, serialized = publisher._producer.sent[0]  # type: ignore[attr-defined]
    assert topic == "scry.ingestion.complete"

    buffer = io.BytesIO(serialized)
    record = cast(
        dict[str, Any],
        schemaless_reader(buffer, INGESTION_EVENT_SCHEMA, INGESTION_EVENT_SCHEMA),
    )

    assert record["correlation_id"] == "corr-xyz"
    assert record["adapter"] == "JSONAdapter"
    assert record["duration_ms"] == 150
    assert record["validation"]["error_count"] == 0
    assert record["validation"]["warning_count"] == 1
    assert record["metrics"]["record_count"] == "10"

    publisher.close()
    get_settings.cache_clear()
