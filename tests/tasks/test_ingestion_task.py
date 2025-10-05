"""Tests for Celery ingestion tasks."""

from __future__ import annotations

import pytest

from scry_ingestor.tasks import INGESTION_TASKS, run_ingestion_pipeline


class StubPublisher:
    """Test double capturing published payloads."""

    def __init__(self) -> None:
        self.published = []

    def publish_success(self, payload) -> None:  # type: ignore[no-untyped-def]
        self.published.append(payload)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure cached settings do not leak between tests."""

    from scry_ingestor.utils.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_run_ingestion_pipeline_publishes_event(
    monkeypatch: pytest.MonkeyPatch, sample_json_config
):
    """Successful ingestion should publish an event and return serialized payload."""

    publisher = StubPublisher()
    monkeypatch.setattr(
        "scry_ingestor.tasks.ingestion.get_ingestion_publisher",
        lambda: publisher,
    )

    payload = {
        "source_config": sample_json_config,
        "correlation_id": "celery-corr-1",
    }

    result = run_ingestion_pipeline("json", payload)

    assert publisher.published, "Expected the Kafka publisher to record a message."
    published_payload = publisher.published[0]
    assert published_payload.metadata.correlation_id == "celery-corr-1"
    assert result["status"] == "success"
    assert result["payload"]["metadata"]["correlation_id"] == "celery-corr-1"
    assert result["payload"]["metadata"]["adapter_type"] == "JSONAdapter"


def test_registered_tasks_include_json_adapter():
    """The registry should expose a Celery task for each known adapter."""

    assert "json" in INGESTION_TASKS
    task = INGESTION_TASKS["json"]
    assert task.name == "ingest_json_task"

    payload = {
        "source_config": {
            "source_id": "test-json-source",
            "source_type": "file",
            "path": "tests/fixtures/sample.json",
            "use_cloud_processing": False,
        }
    }

    # Call the task's run method directly to avoid Celery broker dependencies.
    result = task.run(payload)
    assert result["status"] == "success"
    assert result["payload"]["metadata"]["adapter_type"] == "JSONAdapter"
