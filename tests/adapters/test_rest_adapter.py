"""Test suite for RESTAdapter using HTTPX MockTransport."""

import json
from typing import Any

import httpx
import pytest

from scry_ingestor.adapters.rest_adapter import RESTAdapter
from scry_ingestor.exceptions import CollectionError, TransformationError


def build_transport(
    status_code: int,
    data: Any,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.MockTransport:
    """Create a mock transport that returns the given response payload."""

    response_headers = {"content-type": "application/json"}
    if headers:
        response_headers.update(headers)

    async def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else data
        return httpx.Response(
            status_code,
            headers=response_headers,
            content=content,
            request=request,
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def base_config() -> dict[str, Any]:
    """Base REST adapter configuration used across tests."""

    return {
        "source_id": "rest-test",
        "endpoint": "https://api.example.com/data",
        "method": "GET",
        "query_params": {"limit": "10"},
        "headers": {"Accept": "application/json"},
        "validation": {"expected_statuses": [200]},
        "transformation": {"response_format": "json"},
    }


@pytest.mark.asyncio
async def test_collect_success(base_config: dict[str, Any]) -> None:
    """Collect should perform an HTTP request and capture response metadata."""

    transport = build_transport(200, {"items": []})
    base_config["_transport"] = transport

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 200
    assert raw["request"]["method"] == "GET"
    assert raw["request"]["params"] == {"limit": "10"}
    assert raw["headers"]["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_collect_invalid_method(base_config: dict[str, Any]) -> None:
    """Unsupported HTTP methods should raise CollectionError."""

    base_config["method"] = "TRACE"
    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError):
        await adapter.collect()


@pytest.mark.asyncio
async def test_validate_status_mismatch(base_config: dict[str, Any]) -> None:
    """Validation should mark responses with unexpected status codes as invalid."""

    transport = build_transport(500, {"error": "server"})
    base_config["_transport"] = transport

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()
    validation = await adapter.validate(raw)

    assert validation.is_valid is False
    assert any("Unexpected status code" in err for err in validation.errors)


@pytest.mark.asyncio
async def test_transform_json_body(base_config: dict[str, Any]) -> None:
    """Transform should parse JSON bodies when requested."""

    payload = {"items": [1, 2, 3]}
    base_config["_transport"] = build_transport(200, payload)

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()
    transformed = await adapter.transform(raw)

    assert transformed["body"] == payload


@pytest.mark.asyncio
async def test_transform_text_body(base_config: dict[str, Any]) -> None:
    """Transform should handle text responses when configured."""

    transport = build_transport(200, "ok", headers={"content-type": "text/plain"})
    base_config["_transport"] = transport
    base_config["transformation"] = {"response_format": "text"}

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()
    transformed = await adapter.transform(raw)

    assert transformed["body"] == "ok"


@pytest.mark.asyncio
async def test_transform_invalid_json_raises(base_config: dict[str, Any]) -> None:
    """Invalid JSON should raise a TransformationError when JSON is required."""

    transport = build_transport(200, "not-json", headers={"content-type": "application/json"})
    base_config["_transport"] = transport
    base_config["transformation"] = {"response_format": "json"}

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()

    with pytest.raises(TransformationError):
        await adapter.transform(raw)


@pytest.mark.asyncio
async def test_process_full_pipeline(base_config: dict[str, Any]) -> None:
    """End-to-end process should return payload with metadata and validation."""

    payload = {"message": "success"}
    base_config["_transport"] = build_transport(200, payload)

    adapter = RESTAdapter(base_config)
    result = await adapter.process()

    assert result.data["body"] == payload
    assert result.metadata.adapter_type == "RESTAdapter"
    assert result.validation.is_valid is True
