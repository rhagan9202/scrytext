"""Tests for ingestion observability integrations."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from scry_ingestor.api.main import app
from scry_ingestor.utils.config import get_settings


class StubPublisher:
    """Test double capturing published ingestion payloads."""

    def __init__(self) -> None:
        self.published: list = []

    def publish_success(self, payload) -> None:  # type: ignore[no-untyped-def]
        self.published.append(payload)


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide a FastAPI test client with API key authentication configured."""

    monkeypatch.setenv("SCRY_API_KEYS", '["valid-key"]')
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()


def _metric_value(metric: str, labels: dict[str, str] | None = None) -> float:
    """Helper to retrieve the current value of a Prometheus metric sample."""

    labels = labels or {}
    value = REGISTRY.get_sample_value(metric, labels)
    return float(value) if value is not None else 0.0


def test_successful_ingestion_publishes_event_and_updates_metrics(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful ingestion should publish a Kafka event and increment metrics."""

    publisher = StubPublisher()
    monkeypatch.setattr(
        "scry_ingestor.api.routes.ingestion.get_ingestion_publisher",
        lambda: publisher,
    )

    success_before = _metric_value(
        "ingestion_attempts_total",
        {"adapter": "JSONAdapter", "status": "success"},
    )
    duration_before = _metric_value("processing_duration_seconds_count")

    payload = {
        "adapter_type": "json",
        "source_config": {
            "source_id": "test-json-source",
            "source_type": "file",
            "path": "tests/fixtures/sample.json",
            "use_cloud_processing": False,
        },
        "correlation_id": "corr-123",
    }

    response = client.post(
        "/api/v1/ingest",
        json=payload,
        headers={"X-API-Key": "valid-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["payload"]["metadata"]["correlation_id"] == "corr-123"

    success_after = _metric_value(
        "ingestion_attempts_total",
        {"adapter": "JSONAdapter", "status": "success"},
    )
    duration_after = _metric_value("processing_duration_seconds_count")

    assert success_after == pytest.approx(success_before + 1)
    assert duration_after == pytest.approx(duration_before + 1)

    assert len(publisher.published) == 1
    published_payload = publisher.published[0]
    assert published_payload.metadata.adapter_type == "JSONAdapter"
    assert published_payload.metadata.correlation_id == "corr-123"


def test_metrics_endpoint_exposes_prometheus_output(client: TestClient) -> None:
    """The /metrics endpoint should expose Prometheus-formatted metrics."""

    response = client.get("/metrics", headers={"X-API-Key": "valid-key"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert b"ingestion_attempts_total" in response.content
