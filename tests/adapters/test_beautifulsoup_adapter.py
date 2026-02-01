"""Tests for BeautifulSoupAdapter using mocked HTTP responses."""

from typing import Any

import httpx
import pytest

from scry_ingestor.adapters.beautifulsoup_adapter import BeautifulSoupAdapter
from scry_ingestor.exceptions import CollectionError, ConfigurationError


def build_transport(
  html: str,
  status_code: int = 200,
  *,
  headers: dict[str, str] | None = None,
) -> httpx.MockTransport:
    """Create a mock transport that returns the provided HTML content."""

    response_headers = {"content-type": "text/html"}
    if headers:
        response_headers.update(headers)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers=response_headers,
            text=html,
            request=request,
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_collect_success(soup_adapter_config: dict[str, Any]) -> None:
    """Collect should perform an HTTP request and capture response details."""

    html = """
    <html><head><title>Example</title></head>
    <body><article><h1>Headline</h1><p class='summary'>Summary</p></article></body>
    </html>
    """
    soup_adapter_config["_transport"] = build_transport(html)

    adapter = BeautifulSoupAdapter(soup_adapter_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 200
    assert raw["url"].endswith("/articles")
    assert raw["request"]["method"] == "GET"
    assert "content" in raw


@pytest.mark.asyncio
async def test_collect_rejects_method(soup_adapter_config: dict[str, Any]) -> None:
    """Unsupported HTTP methods should raise a CollectionError."""

    soup_adapter_config["method"] = "POST"
    adapter = BeautifulSoupAdapter(soup_adapter_config)

    with pytest.raises(CollectionError):
        await adapter.collect()


@pytest.mark.asyncio
async def test_validate_required_selectors(soup_adapter_config: dict[str, Any]) -> None:
    """Validation fails when required selectors are missing."""

    html = "<html><body><p>No articles here</p></body></html>"
    soup_adapter_config["_transport"] = build_transport(html)
    soup_adapter_config["validation"] = {"required_selectors": ["article h1"]}

    adapter = BeautifulSoupAdapter(soup_adapter_config)
    raw = await adapter.collect()
    validation = await adapter.validate(raw)

    assert validation.is_valid is False
    assert any("Required selector" in err for err in validation.errors)


@pytest.mark.asyncio
async def test_transform_extracts_selectors(soup_adapter_config: dict[str, Any]) -> None:
    """Transform should parse HTML and return structured fields."""

    html = """
    <html>
      <head>
        <title>Example Page</title>
        <meta name='description' content='A demo page.' />
      </head>
      <body>
        <article>
          <h1>First Headline</h1>
          <p class='summary'>First summary.</p>
          <a href='https://example.com/1'>Read more</a>
        </article>
        <article>
          <h1>Second Headline</h1>
          <p class='summary'>Second summary.</p>
          <a href='https://example.com/2'>Continue</a>
        </article>
      </body>
    </html>
    """
    soup_adapter_config["_transport"] = build_transport(html)

    adapter = BeautifulSoupAdapter(soup_adapter_config)
    raw = await adapter.collect()
    validation = await adapter.validate(raw)
    transformed = await adapter.transform(raw)

    assert validation.is_valid is True
    assert transformed["title"] == "Example Page"
    assert len(transformed["links"]) == 2
    assert transformed["extracted"]["headlines"] == ["First Headline", "Second Headline"]
    assert transformed["extracted"]["summaries"] == ["First summary.", "Second summary."]
    assert any(meta.get("name") == "description" for meta in transformed["metadata"])


@pytest.mark.asyncio
async def test_invalid_selector_type_raises_configuration_error(
    soup_adapter_config: dict[str, Any]
) -> None:
    """Non-string selectors should be rejected during configuration."""

    html = "<html><body><article><h1>Headline</h1></article></body></html>"
    soup_adapter_config["_transport"] = build_transport(html)
    soup_adapter_config["transformation"]["selectors"] = {"headlines": ["article h1"]}

    with pytest.raises(ConfigurationError):
        BeautifulSoupAdapter(soup_adapter_config)


@pytest.mark.asyncio
async def test_process_full_pipeline(soup_adapter_config: dict[str, Any]) -> None:
    """End-to-end process should return payload with extracted fields."""

    html = """
    <html>
      <head><title>Pipeline</title></head>
      <body>
        <article>
          <h1>Pipeline Headline</h1>
          <p class='summary'>Pipeline summary.</p>
        </article>
      </body>
    </html>
    """
    soup_adapter_config["_transport"] = build_transport(html)

    adapter = BeautifulSoupAdapter(soup_adapter_config)
    payload = await adapter.process()

    assert payload.metadata.adapter_type == "BeautifulSoupAdapter"
    assert payload.validation.is_valid is True
    assert payload.data["extracted"]["headlines"] == ["Pipeline Headline"]


@pytest.mark.asyncio
async def test_collect_retries_transient_timeout(soup_adapter_config: dict[str, Any]) -> None:
  """Retry policy should recover from transient timeouts."""

  attempts = 0

  async def handler(request: httpx.Request) -> httpx.Response:
    nonlocal attempts
    attempts += 1
    if attempts < 2:
      raise httpx.TimeoutException("simulated timeout")
    return httpx.Response(200, text="<html><body>ok</body></html>", request=request)

  soup_adapter_config["retry"] = {
    "enabled": True,
    "max_attempts": 3,
    "backoff_factor": 0.01,
    "max_backoff": 0.02,
    "jitter": 0.0,
  }
  soup_adapter_config["_transport"] = httpx.MockTransport(handler)

  adapter = BeautifulSoupAdapter(soup_adapter_config)
  raw = await adapter.collect()

  assert raw["status_code"] == 200
  assert attempts == 2


@pytest.mark.asyncio
async def test_collect_returns_last_response_after_retry_exhaustion(
  soup_adapter_config: dict[str, Any]
) -> None:
  """When all retries fail, the final HTTP response should be returned."""

  attempts = 0

  async def handler(request: httpx.Request) -> httpx.Response:
    nonlocal attempts
    attempts += 1
    return httpx.Response(503, text="<html>Error</html>", request=request)

  soup_adapter_config["retry"] = {
    "enabled": True,
    "max_attempts": 2,
    "backoff_factor": 0.01,
    "max_backoff": 0.02,
    "jitter": 0.0,
  }
  soup_adapter_config["_transport"] = httpx.MockTransport(handler)

  adapter = BeautifulSoupAdapter(soup_adapter_config)
  raw = await adapter.collect()

  assert raw["status_code"] == 503
  assert attempts == 2


@pytest.mark.asyncio
async def test_collect_disallows_unlisted_host(soup_adapter_config: dict[str, Any]) -> None:
  """Collection should reject URLs outside the configured allowlist."""

  soup_adapter_config["allowed_hosts"] = ["example.com"]
  soup_adapter_config["url"] = "https://unauthorized.example.net/page"
  soup_adapter_config["_transport"] = build_transport("<html></html>")

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="not permitted"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_allows_regex_pattern(soup_adapter_config: dict[str, Any]) -> None:
  """Regex allowlists should permit matching URLs."""

  soup_adapter_config["allowed_url_patterns"] = [r"https://example\.com/.*"]
  soup_adapter_config["_transport"] = build_transport("<html></html>")

  adapter = BeautifulSoupAdapter(soup_adapter_config)
  raw = await adapter.collect()

  assert raw["status_code"] == 200


@pytest.mark.asyncio
async def test_collect_enforces_max_content_length(soup_adapter_config: dict[str, Any]) -> None:
  """Responses exceeding max_content_length should raise CollectionError."""

  soup_adapter_config["max_content_length"] = 16
  big_html = "<html><body>" + ("x" * 100) + "</body></html>"
  soup_adapter_config["_transport"] = build_transport(
    big_html,
    headers={"content-length": "16"},
  )

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="max_content_length"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_respects_declared_content_length_guardrail(
  soup_adapter_config: dict[str, Any]
) -> None:
  """Responses declaring excessive content-length should be rejected."""

  soup_adapter_config["max_content_length"] = 1024
  html = "<html><body>ok</body></html>"
  soup_adapter_config["_transport"] = build_transport(
    html,
    headers={"content-length": "65536"},
  )

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="Content-Length"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_blocks_redirects_when_disallowed(
  soup_adapter_config: dict[str, Any],
) -> None:
  """Redirect responses should raise when redirects are disabled."""

  soup_adapter_config["allowed_hosts"] = ["example.com"]
  soup_adapter_config["url"] = "https://example.com/redirect"

  async def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
      302,
      headers={"Location": "https://example.com/final"},
      request=request,
    )

  soup_adapter_config["_transport"] = httpx.MockTransport(handler)

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="Redirect responses"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_revalidates_allowlist_after_redirect(
  soup_adapter_config: dict[str, Any],
) -> None:
  """Allowlist enforcement should run after following redirects."""

  soup_adapter_config["allowed_hosts"] = ["example.com"]
  soup_adapter_config["url"] = "https://example.com/redirect"
  soup_adapter_config["follow_redirects"] = True

  async def handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "example.com":
      return httpx.Response(
        302,
        headers={"Location": "https://malicious.example.net/final"},
        request=request,
      )
    return httpx.Response(
      200,
      text="<html><body>ok</body></html>",
      request=request,
    )

  soup_adapter_config["_transport"] = httpx.MockTransport(handler)

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="allowlist"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_blocks_private_network_host_by_default(
  soup_adapter_config: dict[str, Any]
) -> None:
  """Private hosts should raise unless explicitly allowed."""

  soup_adapter_config["url"] = "http://127.0.0.1/page"
  soup_adapter_config["_transport"] = build_transport("<html></html>")

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="Private network hosts"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_allows_private_host_when_opted_in(
  soup_adapter_config: dict[str, Any]
) -> None:
  """Opting in to private networks should permit localhost fetching."""

  soup_adapter_config["url"] = "http://127.0.0.1/page"
  soup_adapter_config["allow_private_networks"] = True
  soup_adapter_config["allowed_hosts"] = ["127.0.0.1"]
  soup_adapter_config["_transport"] = build_transport("<html><body>ok</body></html>")

  adapter = BeautifulSoupAdapter(soup_adapter_config)
  raw = await adapter.collect()

  assert raw["status_code"] == 200
  assert raw["url"].startswith("http://127.0.0.1")


@pytest.mark.asyncio
async def test_collect_requires_allowlist_for_redirects(
  soup_adapter_config: dict[str, Any]
) -> None:
  """Enabling redirects without an allowlist should raise."""

  soup_adapter_config["follow_redirects"] = True
  soup_adapter_config["_transport"] = build_transport("<html></html>")

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="follow_redirects"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_rejects_invalid_timeout(
  soup_adapter_config: dict[str, Any]
) -> None:
  """Zero or negative timeouts should be rejected."""

  soup_adapter_config["timeout"] = -1

  adapter = BeautifulSoupAdapter(soup_adapter_config)

  with pytest.raises(CollectionError, match="timeout must be greater than zero"):
    await adapter.collect()
