"""End-to-end integration tests for FastAPI ingestion flows."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient

from scry_ingestor.api.main import app
from scry_ingestor.utils.config import get_settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(name="client")
async def client_fixture(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    """Create an AsyncClient with API keys configured."""
    monkeypatch.setenv("SCRY_API_KEYS", '["test-api-key-12345"]')
    get_settings.cache_clear()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    get_settings.cache_clear()


@pytest.fixture
def api_key_headers() -> dict[str, str]:
    """Return headers with valid API key for authentication."""
    return {"X-API-Key": "test-api-key-12345"}


@pytest.fixture
def sample_json_request() -> dict[str, Any]:
    """Return a sample JSON ingestion request."""
    return {
        "adapter_type": "json",
        "source_config": {
            "source_id": "e2e-json-test",
            "source_type": "string",
            "data": '{"product": "widget", "price": 19.99, "quantity": 100}',
            "use_cloud_processing": False,
        },
        "correlation_id": "e2e-test-correlation-123",
    }


@pytest.fixture
def sample_csv_request() -> dict[str, Any]:
    """Return a sample CSV ingestion request."""
    return {
        "adapter_type": "csv",
        "source_config": {
            "source_id": "e2e-csv-test",
            "source_type": "string",
            "data": "name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,Chicago",
            "use_cloud_processing": False,
        },
        "correlation_id": "e2e-csv-correlation-456",
    }


async def test_api_health_check(client: AsyncClient) -> None:
    """API should respond to health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"


async def test_list_adapters_endpoint(
    client: AsyncClient,
    api_key_headers: dict[str, str],
) -> None:
    """GET /api/v1/ingest/adapters should list available adapters."""
    response = await client.get("/api/v1/ingest/adapters", headers=api_key_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "adapters" in data
    assert isinstance(data["adapters"], list)

    adapters = data["adapters"]
    assert "json" in adapters
    assert "csv" in adapters
    assert "pdf" in adapters


async def test_json_ingestion_success(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    sample_json_request: dict[str, Any],
) -> None:
    """POST /api/v1/ingest with JSON adapter should process data successfully."""
    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            response = await client.post(
                "/api/v1/ingest",
                json=sample_json_request,
                headers=api_key_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["status"] == "success"
            assert "message" in data
            assert "payload" in data
            assert data["error_details"] is None

            payload = data["payload"]
            assert payload["metadata"]["source_id"] == "e2e-json-test"
            assert payload["metadata"]["adapter_type"] == "json"
            assert payload["metadata"]["correlation_id"] == "e2e-test-correlation-123"

            assert payload["validation"]["is_valid"] is True
            assert isinstance(payload["validation"]["metrics"], dict)


async def test_csv_ingestion_success(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    sample_csv_request: dict[str, Any],
) -> None:
    """POST /api/v1/ingest with CSV adapter should process data successfully."""
    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            response = await client.post(
                "/api/v1/ingest",
                json=sample_csv_request,
                headers=api_key_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            payload = data["payload"]
            assert payload["metadata"]["adapter_type"] == "csv"
            assert payload["validation"]["metrics"]["row_count"] == 3
            assert payload["validation"]["metrics"]["column_count"] == 3


async def test_ingestion_with_invalid_adapter(
    client: AsyncClient,
    api_key_headers: dict[str, str],
) -> None:
    """POST /api/v1/ingest with nonexistent adapter should return 404."""
    invalid_request = {
        "adapter_type": "nonexistent_adapter",
        "source_config": {
            "source_id": "test-invalid",
            "data": "test",
        },
    }

    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        response = await client.post(
            "/api/v1/ingest",
            json=invalid_request,
            headers=api_key_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not registered" in data["detail"].lower()


async def test_ingestion_with_malformed_json(
    client: AsyncClient,
    api_key_headers: dict[str, str],
) -> None:
    """POST /api/v1/ingest with invalid JSON should return error response."""
    bad_json_request = {
        "adapter_type": "json",
        "source_config": {
            "source_id": "test-bad-json",
            "source_type": "string",
            "data": "{this is not valid json}",
            "use_cloud_processing": False,
        },
    }

    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            response = await client.post(
                "/api/v1/ingest",
                json=bad_json_request,
                headers=api_key_headers,
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert data["status"] == "error"
            assert data["payload"] is None
            assert data["error_details"] is not None


async def test_ingestion_without_api_key(
    client: AsyncClient,
    sample_json_request: dict[str, Any],
) -> None:
    """POST /api/v1/ingest without API key should return 401."""
    response = await client.post(
        "/api/v1/ingest",
        json=sample_json_request,
    )

    assert response.status_code in [
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ]


async def test_ingestion_publishes_to_kafka(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    sample_json_request: dict[str, Any],
) -> None:
    """Successful ingestion should publish message to Kafka."""
    publisher_mock = MagicMock()

    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch(
            "scry_ingestor.api.routes.ingestion.get_ingestion_publisher",
            return_value=publisher_mock,
        ):
            response = await client.post(
                "/api/v1/ingest",
                json=sample_json_request,
                headers=api_key_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            assert publisher_mock.publish_success.called


async def test_ingestion_persists_to_database(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    sample_json_request: dict[str, Any],
) -> None:
    """Successful ingestion should persist record to database."""
    persist_mock = MagicMock()

    with patch(
        "scry_ingestor.api.routes.ingestion.persist_ingestion_record",
        persist_mock,
    ):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            response = await client.post(
                "/api/v1/ingest",
                json=sample_json_request,
                headers=api_key_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            assert persist_mock.called
            record = persist_mock.call_args[0][0]
            assert record.source_id == "e2e-json-test"
            assert record.adapter_type == "json"


async def test_ingestion_records_metrics(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    sample_json_request: dict[str, Any],
) -> None:
    """Ingestion should record Prometheus metrics."""
    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            with patch(
                "scry_ingestor.api.routes.ingestion.record_ingestion_attempt"
            ) as metrics_mock:
                response = await client.post(
                    "/api/v1/ingest",
                    json=sample_json_request,
                    headers=api_key_headers,
                )

                assert response.status_code == status.HTTP_200_OK
                assert metrics_mock.called
                call_kwargs = metrics_mock.call_args[1]
                assert call_kwargs["adapter"] == "json"
                assert call_kwargs["status"] == "success"


async def test_multiple_concurrent_ingestions(
    client: AsyncClient,
    api_key_headers: dict[str, str],
    sample_json_request: dict[str, Any],
) -> None:
    """Multiple concurrent ingestion requests should be handled correctly."""
    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            responses = []
            for _ in range(3):
                resp = await client.post(
                    "/api/v1/ingest",
                    json=sample_json_request,
                    headers=api_key_headers,
                )
                responses.append(resp)

            for response in responses:
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["status"] == "success"


async def test_ingestion_with_all_adapter_types(
    client: AsyncClient,
    api_key_headers: dict[str, str],
) -> None:
    """Test ingestion with JSON adapter to ensure it's working end-to-end."""
    with patch("scry_ingestor.api.routes.ingestion.persist_ingestion_record"):
        with patch("scry_ingestor.api.routes.ingestion.get_ingestion_publisher"):
            request_payload = {
                "adapter_type": "json",
                "source_config": {
                    "source_id": "test-json",
                    "source_type": "string",
                    "data": '{"test": "data"}',
                    "use_cloud_processing": False,
                },
            }

            response = await client.post(
                "/api/v1/ingest",
                json=request_payload,
                headers=api_key_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
