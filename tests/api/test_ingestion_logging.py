"""Structured logging tests for ingestion routes."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from scry_ingestor.api.main import app
from scry_ingestor.models.base import reset_engine, session_scope
from scry_ingestor.models.ingestion_record import IngestionRecord
from scry_ingestor.utils.config import get_settings

pytestmark = pytest.mark.asyncio


class StubPublisher:
    """Test double capturing published payloads."""

    def __init__(self) -> None:
        self.published: list = []

    def publish_success(self, payload) -> None:  # type: ignore[no-untyped-def]
        self.published.append(payload)


@pytest.fixture(name="client")
async def client_fixture(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient with API keys configured."""
    monkeypatch.setenv("SCRY_API_KEYS", '["valid-key"]')
    get_settings.cache_clear()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    get_settings.cache_clear()


def _patch_publisher(monkeypatch: pytest.MonkeyPatch) -> StubPublisher:
    publisher = StubPublisher()
    monkeypatch.setattr(
        "scry_ingestor.api.routes.ingestion.get_ingestion_publisher",
        lambda: publisher,
    )
    return publisher


@pytest.fixture
def configured_db(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory):
    """Configure an isolated SQLite database for API persistence tests."""
    db_path = tmp_path_factory.mktemp("api-db") / "ingestion.sqlite"
    monkeypatch.setenv("SCRY_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_engine()
    yield
    reset_engine()
    monkeypatch.delenv("SCRY_DATABASE_URL", raising=False)
    get_settings.cache_clear()


async def test_success_log_includes_validation_summary(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Successful ingestion should emit a log with correlation ID and validation summary."""
    _patch_publisher(monkeypatch)

    payload = {
        "adapter_type": "json",
        "source_config": {
            "source_id": "test-json-source",
            "source_type": "file",
            "path": "tests/fixtures/sample.json",
            "use_cloud_processing": False,
        },
        "correlation_id": "corr-log-1",
    }

    with caplog.at_level(logging.INFO):
        response = await client.post(
            "/api/v1/ingest",
            json=payload,
            headers={"X-API-Key": "valid-key"},
        )

    assert response.status_code == 200

    success_logs = [record for record in caplog.records if "Ingestion success" in record.message]
    assert success_logs, "Expected at least one success log entry."

    record = success_logs[-1]
    assert getattr(record, "correlation_id", None) == "corr-log-1"

    summary_raw = getattr(record, "validation_summary", "{}")
    summary = json.loads(summary_raw)
    assert summary["is_valid"] is True
    assert summary["error_count"] == 0
    assert summary["warning_count"] == 0
    assert summary["metrics"]["valid_json"] is True


async def test_error_log_includes_validation_summary(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Failed ingestion should log correlation ID and validation summary placeholder."""
    _patch_publisher(monkeypatch)

    payload = {
        "adapter_type": "json",
        "source_config": {
            "source_id": "missing-json",
            "source_type": "file",
            "path": "tests/fixtures/does-not-exist.json",
            "use_cloud_processing": False,
        },
        "correlation_id": "corr-log-2",
    }

    with caplog.at_level(logging.ERROR):
        response = await client.post(
            "/api/v1/ingest",
            json=payload,
            headers={"X-API-Key": "valid-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"

    error_logs = [record for record in caplog.records if "Ingestion error" in record.message]
    assert error_logs, "Expected at least one error log entry."

    record = error_logs[-1]
    assert getattr(record, "correlation_id", None) == "corr-log-2"

    summary_raw = getattr(record, "validation_summary", "{}")
    summary = json.loads(summary_raw)
    assert summary["is_valid"] is False
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 0
    assert summary["errors"]
    assert "does-not-exist.json" in summary["errors"][0]


async def test_missing_adapter_logs_correlation_id(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Adapter lookups that fail should log correlation and adapter fields."""
    payload = {
        "adapter_type": "missing-adapter",
        "source_config": {
            "source_id": "missing-src",
        },
        "correlation_id": "corr-missing-adapter",
    }

    with caplog.at_level(logging.ERROR):
        response = await client.post(
            "/api/v1/ingest",
            json=payload,
            headers={"X-API-Key": "valid-key"},
        )

    assert response.status_code == 404

    adapter_logs = [record for record in caplog.records if "Adapter not found" in record.message]
    assert adapter_logs, "Expected an adapter-not-found log entry."

    record = adapter_logs[-1]
    assert getattr(record, "correlation_id", None) == "corr-missing-adapter"
    assert getattr(record, "adapter_type", None) == "missing-adapter"
    assert getattr(record, "status", None) == "error"


async def test_success_persists_ingestion_record(
    configured_db: None, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful ingestions should be stored in the ingestion records table."""
    _patch_publisher(monkeypatch)

    payload = {
        "adapter_type": "json",
        "source_config": {
            "source_id": "persist-json-source",
            "source_type": "file",
            "path": "tests/fixtures/sample.json",
            "use_cloud_processing": False,
        },
        "correlation_id": "corr-persist-success",
    }

    response = await client.post(
        "/api/v1/ingest",
        json=payload,
        headers={"X-API-Key": "valid-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"

    with session_scope() as session:
        records = session.query(IngestionRecord).all()

    assert len(records) == 1
    record = records[0]
    assert record.status == "success"
    assert record.adapter_type == "JSONAdapter"
    assert record.source_id == "persist-json-source"
    assert record.correlation_id == "corr-persist-success"
    assert record.validation_summary is not None
    assert record.validation_summary["is_valid"] is True


async def test_error_persists_ingestion_record(
    configured_db: None, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed ingestions should also be persisted with error details."""
    _patch_publisher(monkeypatch)

    payload = {
        "adapter_type": "json",
        "source_config": {
            "source_id": "persist-json-error",
            "source_type": "file",
            "path": "tests/fixtures/does-not-exist.json",
            "use_cloud_processing": False,
        },
        "correlation_id": "corr-persist-error",
    }

    response = await client.post(
        "/api/v1/ingest",
        json=payload,
        headers={"X-API-Key": "valid-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"

    with session_scope() as session:
        records = session.query(IngestionRecord).all()

    assert len(records) == 1
    record = records[0]
    assert record.status == "error"
    assert record.adapter_type == "json"
    assert record.source_id == "persist-json-error"
    assert record.correlation_id == "corr-persist-error"
    assert record.error_details is not None
    assert record.error_details["error_type"] == body["error_details"]["error_type"]
    assert record.validation_summary is not None
    assert record.validation_summary["is_valid"] is False
