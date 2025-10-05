"""Structured logging tests for ingestion routes."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from scry_ingestor.api.main import app
from scry_ingestor.utils.config import get_settings


class StubPublisher:
    """Test double capturing published payloads."""

    def __init__(self) -> None:
        self.published: list = []

    def publish_success(self, payload) -> None:  # type: ignore[no-untyped-def]
        self.published.append(payload)


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide a FastAPI client with API keys configured."""

    monkeypatch.setenv("SCRY_API_KEYS", '["valid-key"]')
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()


def _patch_publisher(monkeypatch: pytest.MonkeyPatch) -> StubPublisher:
    publisher = StubPublisher()
    monkeypatch.setattr(
        "scry_ingestor.api.routes.ingestion.get_ingestion_publisher",
        lambda: publisher,
    )
    return publisher


def test_success_log_includes_validation_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
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
        response = client.post(
            "/api/v1/ingest",
            json=payload,
            headers={"X-API-Key": "valid-key"},
        )

    assert response.status_code == 200

    success_logs = [record for record in caplog.records if "Ingestion success" in record.message]
    assert success_logs, "Expected at least one success log entry."

    record = success_logs[-1]
    assert record.correlation_id == "corr-log-1"

    summary = json.loads(record.validation_summary)
    assert summary["is_valid"] is True
    assert summary["error_count"] == 0
    assert summary["warning_count"] == 0
    assert summary["metrics"]["valid_json"] is True


def test_error_log_includes_validation_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
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
        response = client.post(
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
    assert record.correlation_id == "corr-log-2"

    summary = json.loads(record.validation_summary)
    assert summary["is_valid"] is False
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 0
    assert summary["errors"]
    assert "does-not-exist.json" in summary["errors"][0]
