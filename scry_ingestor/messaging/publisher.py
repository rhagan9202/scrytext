"""Kafka publisher for ingestion completion events."""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

from fastavro import schemaless_writer
from kafka import KafkaProducer

from ..schemas.payload import IngestionPayload
from ..utils.config import get_settings
from ..utils.logging import setup_logger
from .schema import INGESTION_EVENT_SCHEMA, build_ingestion_event_record

logger = setup_logger(__name__, context={"adapter_type": "IngestionPublisher"})


class IngestionEventPublisher:
    """Publishes ingestion completion events to Kafka."""

    def __init__(self, producer: KafkaProducer | None = None, topic: str | None = None):
        settings = get_settings()
        self.topic = topic or settings.kafka_topic
        self._producer = producer or self._create_producer(settings.kafka_bootstrap_servers)

    @staticmethod
    def _create_producer(bootstrap_servers: str | None) -> KafkaProducer | None:
        if not bootstrap_servers:
            logger.warning(
                "Kafka bootstrap servers not configured; ingestion events will not be published.",
                extra={"status": "warning"},
            )
            return None

        servers = [server.strip() for server in bootstrap_servers.split(",") if server.strip()]
        if not servers:
            logger.warning(
                "Kafka bootstrap configuration is empty after parsing; disabling publisher.",
                extra={"status": "warning"},
            )
            return None

        return KafkaProducer(bootstrap_servers=servers)

    def publish_success(self, payload: IngestionPayload) -> None:
        """Publish a successful ingestion event to Kafka."""

        if self._producer is None or not self.topic:
            return

        record = build_ingestion_event_record(payload, status="success")
        serialized = _serialize_avro(record)

        future = self._producer.send(self.topic, value=serialized)
        try:
            future.get(timeout=5)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to publish ingestion event: %s",
                exc,
                exc_info=True,
                extra={"status": "error"},
            )

    def close(self) -> None:
        """Close the underlying Kafka producer, flushing outstanding messages."""

        if self._producer is not None:
            self._producer.flush()
            self._producer.close()


@lru_cache(maxsize=1)
def get_ingestion_publisher() -> IngestionEventPublisher:
    """Return a cached ingestion event publisher instance."""

    return IngestionEventPublisher()


def _serialize_avro(record: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    schemaless_writer(buffer, INGESTION_EVENT_SCHEMA, record)
    return buffer.getvalue()
