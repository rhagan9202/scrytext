"""Test suite for RESTAdapter using HTTPX MockTransport."""

import json
from typing import Any

import httpx
import pytest

from scry_ingestor.adapters.rest_adapter import RESTAdapter
from scry_ingestor.exceptions import CollectionError, ConfigurationError, TransformationError


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


def test_invalid_response_format_raises_configuration_error(
    base_config: dict[str, Any]
) -> None:
    """Unsupported response formats should be caught upon adapter creation."""

    base_config["transformation"] = {"response_format": "xml"}

    with pytest.raises(ConfigurationError):
        RESTAdapter(base_config)


@pytest.mark.asyncio
async def test_collect_retries_transient_timeout(base_config: dict[str, Any]) -> None:
    """Retry policy should recover from a transient timeout."""

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.TimeoutException("simulated timeout")
        return httpx.Response(200, json={"items": []}, request=request)

    base_config["retry"] = {
        "enabled": True,
        "max_attempts": 3,
        "backoff_factor": 0.01,
        "max_backoff": 0.02,
        "jitter": 0.0,
    }
    base_config["_transport"] = httpx.MockTransport(handler)

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 200
    assert attempts == 2


@pytest.mark.asyncio
async def test_collect_returns_last_response_after_retry_exhaustion(
    base_config: dict[str, Any]
) -> None:
    """When all retry attempts fail, the final HTTP response should be returned."""

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"}, request=request)

    base_config["retry"] = {
        "enabled": True,
        "max_attempts": 2,
        "backoff_factor": 0.01,
        "max_backoff": 0.02,
        "jitter": 0.0,
    }
    base_config["_transport"] = httpx.MockTransport(handler)

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 503
    assert attempts == 2


@pytest.mark.asyncio
async def test_collect_does_not_retry_non_idempotent_methods_by_default(
    base_config: dict[str, Any]
) -> None:
    """Non-idempotent HTTP methods should not be retried unless explicitly configured."""

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.TimeoutException("simulated timeout")

    base_config["method"] = "POST"
    base_config["retry"] = {
        "enabled": True,
        "max_attempts": 3,
        "backoff_factor": 0.01,
        "max_backoff": 0.02,
        "jitter": 0.0,
    }
    base_config["_transport"] = httpx.MockTransport(handler)

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="timed out"):
        await adapter.collect()

    assert attempts == 1


@pytest.mark.asyncio
async def test_collect_disallows_unlisted_host(base_config: dict[str, Any]) -> None:
    """Collection should reject endpoints outside the configured allowlist."""

    base_config["allowed_hosts"] = ["api.example.com"]
    base_config["endpoint"] = "https://unauthorized.example.com/data"
    base_config["_transport"] = build_transport(200, {"ok": True})

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="not permitted"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_allows_regex_pattern(base_config: dict[str, Any]) -> None:
    """Regex allowlists should permit matching URLs."""

    base_config["allowed_url_patterns"] = [r"https://api\.example\.com/.*"]
    base_config["_transport"] = build_transport(200, {"items": []})

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 200


@pytest.mark.asyncio
async def test_collect_enforces_max_content_length(base_config: dict[str, Any]) -> None:
    """Responses larger than max_content_length should raise CollectionError."""

    base_config["max_content_length"] = 4
    base_config["_transport"] = build_transport(
        200,
        b"excess",
        headers={"content-type": "text/plain", "content-length": "4"},
    )

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="max_content_length"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_respects_declared_content_length_guardrail(
    base_config: dict[str, Any]
) -> None:
    """Responses declaring a content-length above the limit must be rejected."""

    base_config["max_content_length"] = 10
    base_config["_transport"] = build_transport(
        200,
        b"short",
        headers={"content-type": "text/plain", "content-length": "2048"},
    )

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="Content-Length"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_blocks_redirects_when_disallowed(base_config: dict[str, Any]) -> None:
    """Redirect responses should raise when redirects are disabled."""

    base_config["allowed_hosts"] = ["api.example.com"]
    base_config["endpoint"] = "https://api.example.com/redirect"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://api.example.com/final"},
            request=request,
        )

    base_config["_transport"] = httpx.MockTransport(handler)

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="Redirect responses"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_revalidates_allowlist_after_redirect(base_config: dict[str, Any]) -> None:
    """Allowlist enforcement should apply after following redirects."""

    base_config["allowed_hosts"] = ["api.example.com"]
    base_config["endpoint"] = "https://api.example.com/redirect"
    base_config["follow_redirects"] = True

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.example.com":
            return httpx.Response(
                302,
                headers={"Location": "https://malicious.example.net/final"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"status": "ok"},
            request=request,
        )

    base_config["_transport"] = httpx.MockTransport(handler)

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="allowlist"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_raises_on_timeout(base_config: dict[str, Any]) -> None:
    """HTTP timeouts should surface as CollectionError instances."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    base_config["_transport"] = httpx.MockTransport(handler)

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="timed out"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_blocks_private_network_host_by_default(
    base_config: dict[str, Any]
) -> None:
    """Private or loopback network hosts should be rejected unless explicitly allowed."""

    base_config["endpoint"] = "http://127.0.0.1/internal"
    base_config["_transport"] = build_transport(200, {"ok": True})

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="Private network hosts"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_allows_private_network_when_opted_in(
    base_config: dict[str, Any]
) -> None:
    """Explicit opt-in should allow private hosts when combined with an allowlist."""

    base_config["endpoint"] = "http://127.0.0.1/internal"
    base_config["allow_private_networks"] = True
    base_config["allowed_hosts"] = ["127.0.0.1"]
    base_config["_transport"] = build_transport(200, {"result": "ok"})

    adapter = RESTAdapter(base_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 200
    assert raw["url"].startswith("http://127.0.0.1")


@pytest.mark.asyncio
async def test_collect_requires_allowlist_for_redirects(base_config: dict[str, Any]) -> None:
    """Enabling redirects without an allowlist should be blocked for safety."""

    base_config["follow_redirects"] = True
    base_config["_transport"] = build_transport(200, {"items": []})

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="follow_redirects"):
        await adapter.collect()


@pytest.mark.asyncio
async def test_collect_rejects_invalid_timeout(base_config: dict[str, Any]) -> None:
    """Non-positive timeouts should raise a CollectionError."""

    base_config["timeout"] = 0

    adapter = RESTAdapter(base_config)

    with pytest.raises(CollectionError, match="timeout must be greater than zero"):
        await adapter.collect()
