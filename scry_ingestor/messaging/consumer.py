"""Kafka consumer for ingestion completion events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from confluent_kafka import Consumer, KafkaException, Message
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext

from ..utils.config import get_settings
from ..utils.logging import setup_logger
from .config import build_consumer_config, build_schema_registry_config
from .schema import INGESTION_EVENT_SCHEMA_STR

logger = setup_logger(__name__, context={"adapter_type": "IngestionConsumer"})


@dataclass(slots=True)
class IngestionEvent:
    """Container for a deserialized ingestion event and the original message."""

    record: dict[str, Any]
    message: Message


class IngestionEventConsumer:
    """Consumes ingestion completion events from Kafka."""

    def __init__(
        self,
        *,
        topic: str | None = None,
        group_id: str | None = None,
        consumer: Consumer | None = None,
        schema_registry_client: SchemaRegistryClient | None = None,
        deserializer: Callable[[bytes | None, SerializationContext], dict[str, Any]] | None = None,
    ) -> None:
        settings = get_settings()

        self.topic = topic or settings.kafka_topic
        self.group_id = group_id or settings.kafka_consumer_group

        self._consumer_config = build_consumer_config(settings, self.group_id)
        self._schema_registry_config = build_schema_registry_config(settings)

        self._consumer = consumer or self._create_consumer()
        self._schema_registry = schema_registry_client or self._create_schema_registry()
        self._deserializer = deserializer or self._create_deserializer()
        self._context = (
            SerializationContext(self.topic, MessageField.VALUE)
            if self.topic and self._deserializer
            else None
        )

        if self._consumer and self.topic:
            self._consumer.subscribe([self.topic])

    def _create_consumer(self) -> Consumer | None:
        if "bootstrap.servers" not in self._consumer_config:
            logger.warning(
                "Kafka bootstrap servers not configured; ingestion consumer disabled.",
                extra={"status": "warning"},
            )
            return None

        try:
            return Consumer(self._consumer_config)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to construct Kafka consumer: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )
            return None

    def _create_schema_registry(self) -> SchemaRegistryClient | None:
        if not self._schema_registry_config:
            logger.warning(
                "Schema registry configuration missing; ingestion consumer disabled.",
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

    def _create_deserializer(
        self,
    ) -> Callable[[bytes | None, SerializationContext], dict[str, Any]] | None:
        if self._schema_registry is None:
            return None

        avro_deserializer = AvroDeserializer(
            schema_registry_client=self._schema_registry,
            schema_str=INGESTION_EVENT_SCHEMA_STR,
        )

        def _deserialize(value: bytes | None, context: SerializationContext) -> dict[str, Any]:
            if value is None:
                raise ValueError("Cannot deserialize empty Kafka message value")
            record = avro_deserializer(value, context)
            if record is None:
                raise ValueError("Avro deserializer returned None")
            return record

        return _deserialize

    def poll(self, timeout: float = 1.0) -> IngestionEvent | None:
        """Poll Kafka for the next ingestion event."""

        if self._consumer is None or self._deserializer is None or self._context is None:
            return None

        message = self._consumer.poll(timeout=timeout)
        if message is None:
            return None

        if message.error():
            raise KafkaException(message.error())

        record = self._deserializer(message.value(), self._context)
        return IngestionEvent(record=record, message=message)

    def commit(self, message: Message | None = None, asynchronous: bool = False) -> None:
        """Commit offsets for processed messages."""

        if self._consumer is None:
            return

        try:
            self._consumer.commit(message=message, asynchronous=asynchronous)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to commit Kafka offset: %s",
                exc,
                extra={"status": "error"},
                exc_info=True,
            )

    def close(self) -> None:
        if self._consumer is not None:
            self._consumer.close()

    def run(self, handler: Callable[[dict[str, Any]], None], poll_timeout: float = 1.0) -> None:
        """Continuously poll for messages and invoke the provided handler."""

        while True:  # pragma: no cover - used in runtime execution
            event = self.poll(timeout=poll_timeout)
            if event is None:
                continue

            try:
                handler(event.record)
                self.commit(event.message)
            except Exception as exc:
                logger.error(
                    "Failed processing ingestion event: %s",
                    exc,
                    extra={"status": "error"},
                    exc_info=True,
                )

    def __enter__(self) -> IngestionEventConsumer:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
