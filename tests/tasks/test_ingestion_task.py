"""Tests for Celery ingestion tasks."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry

from scry_ingestor.adapters.base import BaseAdapter
from scry_ingestor.exceptions import CollectionError, TaskExecutionError
from scry_ingestor.models.base import reset_engine, session_scope
from scry_ingestor.models.ingestion_record import IngestionRecord
from scry_ingestor.schemas.payload import ValidationResult
from scry_ingestor.tasks import INGESTION_TASKS, run_ingestion_pipeline
from scry_ingestor.tasks.circuit_breaker import get_circuit_breaker


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
    get_circuit_breaker().reset()
    yield
    get_settings.cache_clear()
    get_circuit_breaker().reset()


@pytest.fixture
def configured_task_db(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory):
    """Configure isolated database storage for Celery task persistence tests."""

    db_path = tmp_path_factory.mktemp("task-db") / "ingestion.sqlite"
    monkeypatch.setenv("SCRY_DATABASE_URL", f"sqlite:///{db_path}")
    from scry_ingestor.utils.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    yield
    reset_engine()
    monkeypatch.delenv("SCRY_DATABASE_URL", raising=False)
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


def test_run_ingestion_pipeline_persists_success(
    configured_task_db: None, monkeypatch: pytest.MonkeyPatch, sample_json_config
) -> None:
    """Successful pipeline executions should persist ingestion records."""

    publisher = StubPublisher()
    monkeypatch.setattr(
        "scry_ingestor.tasks.ingestion.get_ingestion_publisher",
        lambda: publisher,
    )

    payload = {
        "source_config": sample_json_config,
        "correlation_id": "celery-db-success",
    }

    run_ingestion_pipeline("json", payload)

    with session_scope() as session:
        records = session.query(IngestionRecord).all()

    assert len(records) == 1
    record = records[0]
    assert record.status == "success"
    assert record.correlation_id == "celery-db-success"
    assert record.adapter_type == "JSONAdapter"


def test_run_ingestion_pipeline_persists_error(
    configured_task_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed pipeline executions should also persist ingestion records."""

    publisher = StubPublisher()
    monkeypatch.setattr(
        "scry_ingestor.tasks.ingestion.get_ingestion_publisher",
        lambda: publisher,
    )

    payload = {
        "source_config": {
            "source_id": "task-error-source",
            "source_type": "file",
            "path": "tests/fixtures/does-not-exist.json",
            "use_cloud_processing": False,
        },
        "correlation_id": "celery-db-error",
    }

    with pytest.raises(TaskExecutionError) as excinfo:
        run_ingestion_pipeline("json", payload)

    with session_scope() as session:
        records = session.query(IngestionRecord).all()

    assert len(records) == 1
    record = records[0]
    assert record.status == "error"
    assert record.correlation_id == "celery-db-error"
    assert record.source_id == "task-error-source"
    assert record.error_details is not None
    error_details = record.error_details
    assert error_details["classification"] == "collection"
    assert error_details["retryable"] is False
    details = error_details.get("details") or {}
    assert isinstance(details, dict)
    assert "retry_policy" in details
    assert error_details["error_type"] == "CollectionError"

    report = excinfo.value.report
    assert report.retryable is False


def test_circuit_breaker_blocks_after_threshold(
    configured_task_db: None,
    monkeypatch: pytest.MonkeyPatch,
    sample_json_config: dict[str, Any],
) -> None:
    """Repeated failures should open the circuit breaker and block subsequent runs."""

    monkeypatch.setenv("SCRY_CELERY_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("SCRY_CELERY_FAILURE_WINDOW_SECONDS", "60")
    monkeypatch.setenv("SCRY_CELERY_CIRCUIT_RESET_SECONDS", "60")

    from scry_ingestor.utils.config import get_settings

    get_settings.cache_clear()

    class AlwaysFailAdapter(BaseAdapter):
        async def collect(self) -> Any:  # type: ignore[override]
            raise CollectionError("transient outage")

        async def validate(self, raw_data: Any) -> ValidationResult:
            # pragma: no cover - unreachable due to collection failure
            return ValidationResult(is_valid=False, errors=["failure"], warnings=[], metrics={})

        async def transform(self, raw_data: Any) -> Any:  # pragma: no cover - unreachable
            return {}

    monkeypatch.setattr(
        "scry_ingestor.tasks.ingestion.get_adapter",
        lambda name: AlwaysFailAdapter,
    )

    payload = {
        "source_config": sample_json_config,
        "correlation_id": "breaker-test",
    }

    with pytest.raises(TaskExecutionError) as first_failure:
        run_ingestion_pipeline("json", payload)

    assert first_failure.value.report.classification == "collection"

    with pytest.raises(TaskExecutionError) as circuit_open:
        run_ingestion_pipeline("json", payload)

    assert circuit_open.value.report.classification == "circuit_open"
    assert circuit_open.value.report.retryable is False

    with session_scope() as session:
        records = session.query(IngestionRecord).filter_by(status="error").all()

    assert len(records) == 2
    last_error = records[-1].error_details
    assert last_error is not None
    assert last_error["classification"] == "circuit_open"


def test_celery_task_retries_when_policy_enabled(
    monkeypatch: pytest.MonkeyPatch, sample_json_config: dict[str, Any]
) -> None:
    """Celery task should invoke retry when the error is marked retryable."""

    class RetryAdapter(BaseAdapter):
        async def collect(self) -> Any:  # type: ignore[override]
            raise CollectionError("temporary network disruption")

        async def validate(self, raw_data: Any) -> ValidationResult:
            # pragma: no cover - unreachable due to collection failure
            return ValidationResult(is_valid=False, errors=["failure"], warnings=[], metrics={})

        async def transform(self, raw_data: Any) -> Any:  # pragma: no cover - unreachable
            return {}

    monkeypatch.setattr(
        "scry_ingestor.tasks.ingestion.get_adapter",
        lambda name: RetryAdapter,
    )

    payload = {
        "source_config": {
            **sample_json_config,
            "celery_retry": {
                "enabled": True,
                "max_attempts": 1,
                "backoff_seconds": 1,
                "retryable_errors": ["CollectionError"],
            },
        },
        "correlation_id": "retry-test",
    }

    task = INGESTION_TASKS["json"]
    mock_retry = Mock(side_effect=Retry("retrying"))
    monkeypatch.setattr(task, "retry", mock_retry)
    task.request.retries = 0

    with pytest.raises(Retry):
        task.run(payload)

    mock_retry.assert_called_once()
    kwargs = mock_retry.call_args.kwargs
    assert kwargs["countdown"] == 1
    assert kwargs["max_retries"] == 1
