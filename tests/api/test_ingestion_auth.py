"""Tests for API key enforcement on ingestion routes."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from scry_ingestor.api.main import app
from scry_ingestor.utils.config import get_settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(name="client")
async def client_fixture(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient with API keys configured."""
    monkeypatch.setenv("SCRY_API_KEYS", '["valid-key", "another-key"]')
    get_settings.cache_clear()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    get_settings.cache_clear()


async def test_ingestion_routes_accept_valid_api_key(client: AsyncClient) -> None:
    """Requests with a valid API key succeed."""
    response = await client.get(
        "/api/v1/ingest/adapters",
        headers={"X-API-Key": "valid-key"},
    )

    assert response.status_code == 200
    assert "adapters" in response.json()


async def test_ingestion_routes_reject_missing_api_key(client: AsyncClient) -> None:
    """Requests without an API key are rejected with 401."""
    response = await client.get("/api/v1/ingest/adapters")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing API key."}


async def test_ingestion_routes_reject_invalid_api_key(client: AsyncClient) -> None:
    """Requests with an invalid API key receive 403."""
    response = await client.get(
        "/api/v1/ingest/adapters",
        headers={"X-API-Key": "not-correct"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid API key."}
