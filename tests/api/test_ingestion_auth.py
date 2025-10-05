"""Tests for API key enforcement on ingestion routes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from scry_ingestor.api.main import app
from scry_ingestor.utils.config import get_settings


@pytest.fixture(name="client")
def client_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide a FastAPI test client with API keys configured."""

    monkeypatch.setenv("SCRY_API_KEYS", '["valid-key", "another-key"]')
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_ingestion_routes_accept_valid_api_key(client: TestClient) -> None:
    """Requests with a valid API key succeed."""

    response = client.get("/api/v1/ingest/adapters", headers={"X-API-Key": "valid-key"})

    assert response.status_code == 200
    assert "adapters" in response.json()


def test_ingestion_routes_reject_missing_api_key(client: TestClient) -> None:
    """Requests without an API key are rejected with 401."""

    response = client.get("/api/v1/ingest/adapters")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing API key."}


def test_ingestion_routes_reject_invalid_api_key(client: TestClient) -> None:
    """Requests with an invalid API key receive 403."""

    response = client.get(
        "/api/v1/ingest/adapters",
        headers={"X-API-Key": "not-correct"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid API key."}
