"""Integration tests for Celery tasks using in-memory broker."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from celery import Celery

from scry_ingestor.exceptions import TaskExecutionError
from scry_ingestor.tasks.ingestion import INGESTION_TASKS


@pytest.fixture
def in_memory_celery_app() -> Celery:
    """
    Create a Celery app with in-memory broker for testing.

    Uses 'memory://' transport which is synchronous and ideal for testing.
    """

    test_app = Celery(
        "test_scry_ingestor",
        broker="memory://",
        backend="cache+memory://",
    )

    test_app.conf.update(
        task_always_eager=True,  # Execute tasks synchronously
        task_eager_propagates=True,  # Propagate exceptions
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )

    return test_app


@pytest.fixture
def sample_json_task_payload() -> dict[str, Any]:
    """Return a sample task payload for JSON adapter ingestion."""

    return {
        "source_config": {
            "source_id": "test-json-task",
            "source_type": "string",
            "data": '{"name": "test", "value": 42}',
            "use_cloud_processing": False,
        },
        "correlation_id": "celery-test-123",
    }


@pytest.fixture
def sample_csv_task_payload() -> dict[str, Any]:
    """Return a sample task payload for CSV adapter ingestion."""

    return {
        "source_config": {
            "source_id": "test-csv-task",
            "source_type": "string",
            "data": "id,value\n1,100\n2,200",
            "use_cloud_processing": False,
        },
        "correlation_id": "celery-csv-123",
    }


def test_celery_app_configuration(in_memory_celery_app: Celery) -> None:
    """Celery app should be properly configured for in-memory testing."""

    assert in_memory_celery_app.conf.task_always_eager is True
    assert in_memory_celery_app.conf.broker_url == "memory://"
    assert in_memory_celery_app.conf.result_backend == "cache+memory://"


@pytest.mark.asyncio
async def test_ingestion_task_registration() -> None:
    """Ingestion tasks should be registered in the INGESTION_TASKS registry."""

    # Verify JSON and CSV adapters have registered tasks
    assert "json" in INGESTION_TASKS
    assert "csv" in INGESTION_TASKS

    json_task = INGESTION_TASKS["json"]
    assert json_task is not None
    assert hasattr(json_task, "apply_async")
    assert hasattr(json_task, "delay")


@pytest.mark.asyncio
async def test_json_adapter_task_success(
    in_memory_celery_app: Celery,
    sample_json_task_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON adapter ingestion task should process data successfully."""

    # Patch persistence and publishing to avoid side effects
    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.tasks.ingestion.get_ingestion_publisher"):
            # Get the pre-registered JSON task
            task = INGESTION_TASKS["json"]
            in_memory_celery_app.register_task(task)

            # Execute the task eagerly
            result = task.apply_async(kwargs=sample_json_task_payload)

            # Verify task completed successfully
            assert result.state == "SUCCESS"

            # Get the result payload
            result_data = result.result
            assert result_data is not None
            assert result_data["status"] == "success"
            assert "payload" in result_data

            payload_dict = result_data["payload"]
            assert payload_dict["metadata"]["source_id"] == "test-json-task"
            assert payload_dict["metadata"]["adapter_type"] == "JSONAdapter"
            assert payload_dict["metadata"]["correlation_id"] == "celery-test-123"
            assert payload_dict["validation"]["is_valid"] is True


@pytest.mark.asyncio
async def test_csv_adapter_task_success(
    in_memory_celery_app: Celery,
    sample_csv_task_payload: dict[str, Any],
) -> None:
    """CSV adapter ingestion task should process tabular data successfully."""

    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.tasks.ingestion.get_ingestion_publisher"):
            # Get the pre-registered CSV task
            task = INGESTION_TASKS["csv"]
            in_memory_celery_app.register_task(task)

            # Execute the task
            result = task.apply_async(kwargs=sample_csv_task_payload)

            assert result.state == "SUCCESS"
            result_data = result.result
            payload_dict = result_data["payload"]

            assert payload_dict["metadata"]["adapter_type"] == "CSVAdapter"
            assert payload_dict["validation"]["metrics"]["row_count"] == 2
            assert payload_dict["validation"]["metrics"]["column_count"] == 2


@pytest.mark.asyncio
async def test_task_with_invalid_adapter_key() -> None:
    """Task registry should not contain invalid adapter keys."""

    assert "nonexistent_adapter" not in INGESTION_TASKS
    assert "invalid" not in INGESTION_TASKS


@pytest.mark.asyncio
async def test_task_with_collection_error_handles_failure(
    in_memory_celery_app: Celery,
) -> None:
    """Task should handle collection errors gracefully."""

    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.tasks.ingestion.get_ingestion_publisher"):
            task = INGESTION_TASKS["json"]
            in_memory_celery_app.register_task(task)

            # Invalid JSON will cause collection error
            invalid_payload = {
                "source_config": {
                    "source_id": "test-invalid-json",
                    "source_type": "string",
                    "data": "{invalid json}",
                    "use_cloud_processing": False,
                }
            }

            result = task.apply_async(kwargs=invalid_payload)

            # Task should fail with TaskExecutionError
            assert result.state == "FAILURE"
            assert isinstance(result.info, TaskExecutionError)


@pytest.mark.asyncio
async def test_task_persists_success_record(
    in_memory_celery_app: Celery,
    sample_json_task_payload: dict[str, Any],
) -> None:
    """Successful ingestion tasks should persist records to the database."""

    persist_mock = MagicMock()

    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record", persist_mock):
        with patch("scry_ingestor.tasks.ingestion.get_ingestion_publisher"):
            task = INGESTION_TASKS["json"]
            in_memory_celery_app.register_task(task)

            task.apply_async(kwargs=sample_json_task_payload)

            # Verify persistence was called
            assert persist_mock.called
            call_args = persist_mock.call_args[0][0]
            assert call_args.source_id == "test-json-task"
            assert call_args.status == "success"


@pytest.mark.asyncio
async def test_task_publishes_success_event(
    in_memory_celery_app: Celery,
    sample_json_task_payload: dict[str, Any],
) -> None:
    """Successful ingestion tasks should publish events to Kafka."""

    publisher_mock = MagicMock()

    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record"):
        with patch(
            "scry_ingestor.tasks.ingestion.get_ingestion_publisher",
            return_value=publisher_mock,
        ):
            task = INGESTION_TASKS["json"]
            in_memory_celery_app.register_task(task)

            task.apply_async(kwargs=sample_json_task_payload)

            # Verify publish was called
            assert publisher_mock.publish_success.called


@pytest.mark.asyncio
async def test_task_with_retry_policy(
    in_memory_celery_app: Celery,
) -> None:
    """Task should respect retry policy configuration."""

    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.tasks.ingestion.get_ingestion_publisher"):
            retry_payload = {
                "source_config": {
                    "source_id": "test-retry",
                    "source_type": "string",
                    "data": '{"test": true}',
                    "use_cloud_processing": False,
                    "celery_retry": {
                        "enabled": True,
                        "max_attempts": 3,
                        "backoff_seconds": 1.0,
                        "max_backoff_seconds": 10.0,
                    },
                }
            }

            task = INGESTION_TASKS["json"]
            in_memory_celery_app.register_task(task)

            result = task.apply_async(kwargs=retry_payload)

            # Task should succeed despite retry config
            assert result.state == "SUCCESS"


@pytest.mark.asyncio
async def test_task_records_metrics(
    in_memory_celery_app: Celery,
    sample_json_task_payload: dict[str, Any],
) -> None:
    """Ingestion tasks should record metrics for monitoring."""

    with patch("scry_ingestor.tasks.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.tasks.ingestion.get_ingestion_publisher"):
            with patch("scry_ingestor.tasks.ingestion.record_ingestion_attempt") as metrics_mock:
                task = INGESTION_TASKS["json"]
                in_memory_celery_app.register_task(task)

                task.apply_async(kwargs=sample_json_task_payload)

                # Verify metrics were recorded
                assert metrics_mock.called
                call_kwargs = metrics_mock.call_args[1]
                assert call_kwargs["adapter"] == "JSONAdapter"
                assert call_kwargs["status"] == "success"


@pytest.mark.asyncio
async def test_multiple_adapter_tasks_registered() -> None:
    """Multiple adapter types should have registered tasks."""

    # Check that common adapters are registered
    expected_adapters = ["json", "csv", "pdf", "word", "excel", "rest", "beautifulsoup"]

    for adapter_name in expected_adapters:
        assert adapter_name in INGESTION_TASKS, f"Adapter '{adapter_name}' should be registered"

    # All tasks should be callable
    for task in INGESTION_TASKS.values():
        assert callable(task)
