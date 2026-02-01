"""Kafka publisher for ingestion completion events."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.schema_registry import SchemaRegistryClient, SchemaRegistryError
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

from ..schemas.payload import IngestionPayload
from ..utils.config import get_settings
from ..utils.logging import setup_logger
from .config import build_producer_config, build_schema_registry_config
from .schema import INGESTION_EVENT_SCHEMA_STR, build_ingestion_event_record

logger = setup_logger(__name__, context={"adapter_type": "IngestionPublisher"})


Serializer = Callable[[dict[str, Any], SerializationContext], bytes]


class IngestionEventPublisher:
    """Publishes ingestion completion events to Kafka with Avro serialization."""

    def __init__(
        self,
        *,
        producer: Producer | None = None,
        schema_registry_client: SchemaRegistryClient | None = None,
        serializer: Serializer | None = None,
        topic: str | None = None,
    ) -> None:
        settings = get_settings()

        self.topic = topic or settings.kafka_topic
        self._publish_timeout = settings.kafka_publish_timeout_seconds

        self._producer_config = build_producer_config(settings)
        self._schema_registry_config = build_schema_registry_config(settings)

        self._producer = producer or self._create_producer()
        self._schema_registry = schema_registry_client or self._create_schema_registry()
        self._serializer = serializer or self._create_serializer()
        self._serialization_context = (
            SerializationContext(self.topic, MessageField.VALUE)
            if self.topic and self._serializer
            else None
        )
        self._admin_client: AdminClient | None = None

    def _create_producer(self) -> Producer | None:
        if "bootstrap.servers" not in self._producer_config:
            logger.warning(
                "Kafka bootstrap servers not configured; ingestion events will not be published.",
                extra={"status": "warning"},
            )
            return None

        try:
            return Producer(self._producer_config)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to construct Kafka producer: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )
            return None

    def _create_schema_registry(self) -> SchemaRegistryClient | None:
        if not self._schema_registry_config:
            logger.warning(
                "Schema registry configuration missing; ingestion events will not be serialized.",
                extra={"status": "warning"},
            )
            return None

        try:
            return SchemaRegistryClient(self._schema_registry_config)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to initialize schema registry client: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )
            return None

    def _create_serializer(self) -> Serializer | None:
        if self._schema_registry is None:
            return None

        avro_serializer = AvroSerializer(
            schema_registry_client=self._schema_registry,
            schema_str=INGESTION_EVENT_SCHEMA_STR,
            to_dict=lambda record, _: record,
        )

        def _serialize(record: dict[str, Any], context: SerializationContext) -> bytes:
            return avro_serializer(record, context)

        return _serialize

    def _get_admin_client(self) -> AdminClient | None:
        if self._producer is None:
            return None
        if self._admin_client is None:
            try:
                self._admin_client = AdminClient(self._producer_config)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "Failed to initialize Kafka admin client: %s",
                    exc,
                    extra={"status": "error"},
                    exc_info=True,
                )
                return None
        return self._admin_client

    def publish_success(self, payload: IngestionPayload) -> None:
        """Publish a successful ingestion event to Kafka."""

        if self._producer is None or not self.topic:
            return

        if self._serializer is None or self._serialization_context is None:
            logger.warning(
                "Kafka schema registry unavailable; skipping ingestion event publication.",
                extra={"status": "warning"},
            )
            return

        record = build_ingestion_event_record(payload, status="success")

        try:
            serialized_value = self._serializer(record, self._serialization_context)
        except SchemaRegistryError as exc:  # pragma: no cover - schema errors
            logger.error(
                "Failed to serialize ingestion event: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )
            return

        def _delivery(err, msg):  # pragma: no cover - callback invoked asynchronously
            if err is not None:
                logger.error(
                    "Failed to deliver ingestion event: %s",
                    err,
                    extra={"status": "error"},
                )

        try:
            self._producer.produce(
                topic=self.topic,
                value=serialized_value,
                on_delivery=_delivery,
            )
            self._producer.poll(0)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Kafka publish failed: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )

    def close(self) -> None:
        """Close the underlying Kafka producer, flushing outstanding messages."""

        if self._producer is not None:
            try:
                self._producer.flush(timeout=self._publish_timeout)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Kafka producer flush timed out", extra={"status": "warning"})
            if hasattr(self._producer, "close"):
                try:
                    self._producer.close()
                except Exception:  # pragma: no cover - defensive
                    logger.debug(
                        "Kafka producer close failed",
                        extra={"status": "warning"},
                    )

    def health_status(self, timeout: float = 2.0) -> dict[str, str]:
        """Return Kafka connectivity status for health checks."""

        if not self.topic:
            return {"status": "disabled", "reason": "Kafka topic not configured"}

        if self._producer is None:
            return {"status": "disabled", "reason": "Kafka producer unavailable"}

        if self._serializer is None:
            return {"status": "degraded", "reason": "Schema registry unavailable"}

        admin = self._get_admin_client()
        if admin is None:
            return {"status": "degraded", "reason": "Kafka admin client unavailable"}

        try:
            admin.list_topics(timeout=timeout)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Kafka health check failed: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )
            return {"status": "error", "reason": str(exc)}

        return {"status": "ok"}


@lru_cache(maxsize=1)
def get_ingestion_publisher() -> IngestionEventPublisher:
    """Return a cached ingestion event publisher instance."""

    return IngestionEventPublisher()
