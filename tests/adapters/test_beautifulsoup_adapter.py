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


@pytest.fixture
def base_config() -> dict[str, Any]:
    """Base configuration shared across BeautifulSoup adapter tests."""

    return {
        "source_id": "soup-test",
        "url": "https://example.com/articles",
        "validation": {"expected_statuses": [200]},
        "transformation": {
            "include_links": True,
            "include_metadata": True,
            "selectors": {
                "headlines": "article h1",
                "summaries": "article p.summary",
            },
        },
    }


@pytest.mark.asyncio
async def test_collect_success(base_config: dict[str, Any]) -> None:
    """Collect should perform an HTTP request and capture response details."""

    html = """
    <html><head><title>Example</title></head>
    <body><article><h1>Headline</h1><p class='summary'>Summary</p></article></body>
    </html>
    """
    base_config["_transport"] = build_transport(html)

    adapter = BeautifulSoupAdapter(base_config)
    raw = await adapter.collect()

    assert raw["status_code"] == 200
    assert raw["url"].endswith("/articles")
    assert raw["request"]["method"] == "GET"
    assert "content" in raw


@pytest.mark.asyncio
async def test_collect_rejects_method(base_config: dict[str, Any]) -> None:
    """Unsupported HTTP methods should raise a CollectionError."""

    base_config["method"] = "POST"
    adapter = BeautifulSoupAdapter(base_config)

    with pytest.raises(CollectionError):
        await adapter.collect()


@pytest.mark.asyncio
async def test_validate_required_selectors(base_config: dict[str, Any]) -> None:
    """Validation fails when required selectors are missing."""

    html = "<html><body><p>No articles here</p></body></html>"
    base_config["_transport"] = build_transport(html)
    base_config["validation"] = {"required_selectors": ["article h1"]}

    adapter = BeautifulSoupAdapter(base_config)
    raw = await adapter.collect()
    validation = await adapter.validate(raw)

    assert validation.is_valid is False
    assert any("Required selector" in err for err in validation.errors)


@pytest.mark.asyncio
async def test_transform_extracts_selectors(base_config: dict[str, Any]) -> None:
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
    base_config["_transport"] = build_transport(html)

    adapter = BeautifulSoupAdapter(base_config)
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
    base_config: dict[str, Any]
) -> None:
    """Non-string selectors should be rejected during configuration."""

    html = "<html><body><article><h1>Headline</h1></article></body></html>"
    base_config["_transport"] = build_transport(html)
    base_config["transformation"]["selectors"] = {"headlines": ["article h1"]}

    with pytest.raises(ConfigurationError):
        BeautifulSoupAdapter(base_config)


@pytest.mark.asyncio
async def test_process_full_pipeline(base_config: dict[str, Any]) -> None:
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
    base_config["_transport"] = build_transport(html)

    adapter = BeautifulSoupAdapter(base_config)
    payload = await adapter.process()

    assert payload.metadata.adapter_type == "BeautifulSoupAdapter"
    assert payload.validation.is_valid is True
    assert payload.data["extracted"]["headlines"] == ["Pipeline Headline"]


@pytest.mark.asyncio
async def test_collect_disallows_unlisted_host(base_config: dict[str, Any]) -> None:
  """Collection should reject URLs outside the configured allowlist."""

  base_config["allowed_hosts"] = ["example.com"]
  base_config["url"] = "https://unauthorized.example.net/page"
  base_config["_transport"] = build_transport("<html></html>")

  adapter = BeautifulSoupAdapter(base_config)

  with pytest.raises(CollectionError, match="not permitted"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_allows_regex_pattern(base_config: dict[str, Any]) -> None:
  """Regex allowlists should permit matching URLs."""

  base_config["allowed_url_patterns"] = [r"https://example\.com/.*"]
  base_config["_transport"] = build_transport("<html></html>")

  adapter = BeautifulSoupAdapter(base_config)
  raw = await adapter.collect()

  assert raw["status_code"] == 200


@pytest.mark.asyncio
async def test_collect_enforces_max_content_length(base_config: dict[str, Any]) -> None:
  """Responses exceeding max_content_length should raise CollectionError."""

  base_config["max_content_length"] = 16
  big_html = "<html><body>" + ("x" * 100) + "</body></html>"
  base_config["_transport"] = build_transport(big_html)

  adapter = BeautifulSoupAdapter(base_config)

  with pytest.raises(CollectionError, match="max_content_length"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_blocks_redirects_when_disallowed(base_config: dict[str, Any]) -> None:
  """Redirect responses should raise when redirects are disabled."""

  base_config["allowed_hosts"] = ["example.com"]
  base_config["url"] = "https://example.com/redirect"

  async def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
      302,
      headers={"Location": "https://example.com/final"},
      request=request,
    )

  base_config["_transport"] = httpx.MockTransport(handler)

  adapter = BeautifulSoupAdapter(base_config)

  with pytest.raises(CollectionError, match="Redirect responses"):
    await adapter.collect()


@pytest.mark.asyncio
async def test_collect_revalidates_allowlist_after_redirect(base_config: dict[str, Any]) -> None:
  """Allowlist enforcement should run after following redirects."""

  base_config["allowed_hosts"] = ["example.com"]
  base_config["url"] = "https://example.com/redirect"
  base_config["follow_redirects"] = True

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

  base_config["_transport"] = httpx.MockTransport(handler)

  adapter = BeautifulSoupAdapter(base_config)

  with pytest.raises(CollectionError, match="allowlist"):
    await adapter.collect()
