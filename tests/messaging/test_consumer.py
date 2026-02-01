"""Tests for the Kafka ingestion event consumer."""

from __future__ import annotations

from typing import Any

import pytest

from scry_ingestor.messaging.consumer import IngestionEventConsumer
from scry_ingestor.utils.config import get_settings


class _FakeMessage:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def value(self) -> bytes:
        return self._value

    def error(self):  # pragma: no cover - mirrors confluent-kafka API
        return None


class _FakeConsumer:
    def __init__(self, messages: list[_FakeMessage]) -> None:
        self._messages = messages
        self.subscribed: list[str] | None = None
        self.polled: list[float] = []
        self.commits: list[tuple[Any, bool]] = []
        self.closed = False

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = topics

    def poll(self, timeout: float) -> _FakeMessage | None:
        self.polled.append(timeout)
        return self._messages.pop(0) if self._messages else None

    def commit(
        self, message=None, asynchronous: bool = False
    ) -> None:  # pragma: no cover - mimic API
        self.commits.append((message, asynchronous))

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_poll_returns_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consumer should return deserialized events from Kafka."""

    monkeypatch.setenv("SCRY_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    messages = [_FakeMessage(b"encoded")]
    fake_consumer = _FakeConsumer(messages)
    captured: dict[str, Any] = {}

    def deserializer(value: bytes | None, context: Any) -> dict[str, Any]:
        captured["value"] = value
        captured["context"] = context
        return {"adapter": "json"}

    consumer = IngestionEventConsumer(
        topic="test-topic",
        consumer=fake_consumer,
        schema_registry_client=object(),
        deserializer=deserializer,
    )

    event = consumer.poll(timeout=0.5)
    assert event is not None
    assert event.record == {"adapter": "json"}
    assert fake_consumer.subscribed == ["test-topic"]
    assert captured["value"] == b"encoded"

    consumer.commit(event.message)
    assert fake_consumer.commits == [(event.message, False)]

    consumer.close()
    assert fake_consumer.closed is True


def test_poll_returns_none_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consumer should no-op when Kafka or schema registry are not configured."""

    monkeypatch.delenv("SCRY_KAFKA_BOOTSTRAP_SERVERS", raising=False)

    consumer = IngestionEventConsumer(topic="test-topic")

    assert consumer.poll() is None
    consumer.commit()
    consumer.close()
