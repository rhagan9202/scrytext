"""Adapter for crawling web pages and extracting content with BeautifulSoup."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from fnmatch import fnmatch
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import ValidationError as PydanticValidationError

from ..exceptions import CollectionError, ConfigurationError, TransformationError, ValidationError
from ..schemas.payload import ValidationResult
from ..schemas.transformations import BeautifulSoupTransformationConfig
from .base import BaseAdapter


class BeautifulSoupAdapter(BaseAdapter):
    """Adapter that fetches web pages and parses them with BeautifulSoup."""

    SUPPORTED_METHODS = {"GET", "HEAD"}
    DEFAULT_PARSER = "html.parser"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            self._transformation = BeautifulSoupTransformationConfig.model_validate(
                config.get("transformation") or {}
            )
        except PydanticValidationError as exc:
            raise ConfigurationError(
                f"Invalid BeautifulSoup transformation configuration: {exc}"
            ) from exc

    async def collect(self) -> dict[str, Any]:
        """Fetch HTML content from a remote URL."""

        url = self.config.get("url")
        if not url:
            raise CollectionError("BeautifulSoup adapter requires a 'url' in the config")

        method = (self.config.get("method") or "GET").upper()
        if method not in self.SUPPORTED_METHODS:
            raise CollectionError(f"Unsupported HTTP method: {method}")

        timeout = self._parse_timeout(self.config.get("timeout", 30.0))
        follow_redirects = bool(self.config.get("follow_redirects", False))
        if follow_redirects and not self._allowlist_declared():
            raise CollectionError(
                "follow_redirects requires an allowlist configuration to prevent SSRF"
            )
        max_content_length = self._parse_positive_int(
            self.config.get("max_content_length"),
            "max_content_length",
        )
        headers = self._ensure_mapping(
            self.config.get("headers"),
            error_cls=CollectionError,
            context="headers configuration",
        )
        params = self._ensure_mapping(
            self.config.get("query_params"),
            error_cls=CollectionError,
            context="query parameter configuration",
        )

        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": follow_redirects,
        }
        base_url = self.config.get("base_url")
        if base_url:
            client_kwargs["base_url"] = base_url

        transport = self.config.get("_transport")
        if transport is not None:
            client_kwargs["transport"] = transport

        target_url = self._resolve_request_url(url, base_url)
        self._enforce_url_allowlist(target_url)
        self._enforce_network_policy(target_url)

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.request(method, url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise CollectionError(f"HTTP request timed out after {timeout} seconds") from exc
        except httpx.HTTPError as exc:
            raise CollectionError(f"HTTP request failed: {exc}") from exc

        await response.aread()

        self._enforce_url_allowlist(response.request.url)
        self._enforce_network_policy(response.request.url)

        if not follow_redirects and response.is_redirect:
            raise CollectionError("Redirect responses are disallowed by configuration")

        if max_content_length is not None:
            declared_length = response.headers.get("content-length")
            if declared_length:
                try:
                    declared_value = int(declared_length)
                except ValueError as exc:
                    raise CollectionError("Invalid Content-Length header received") from exc
                if declared_value > max_content_length:
                    raise CollectionError(
                        "Response declared Content-Length exceeding configured limit"
                    )
            if len(response.content) > max_content_length:
                raise CollectionError(
                    "Response body exceeded configured max_content_length guardrail"
                )
        try:
            elapsed_ms = int(response.elapsed.total_seconds() * 1000)
        except (AttributeError, RuntimeError):
            elapsed_ms = 0

        content = response.text
        if method == "HEAD":
            content = ""

        return {
            "url": str(response.request.url),
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": content,
            "elapsed_ms": elapsed_ms,
            "request": {
                "method": method,
                "headers": dict(response.request.headers),
                "params": params,
            },
        }

    async def validate(self, raw_data: dict[str, Any]) -> ValidationResult:
        """Validate response status and optional selector requirements."""

        validation_cfg = self._ensure_mapping(
            self.config.get("validation"),
            error_cls=ValidationError,
            context="validation configuration",
        )

        expected_statuses = validation_cfg.get("expected_statuses", [200])
        if isinstance(expected_statuses, int):
            expected_statuses = [expected_statuses]

        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, Any] = {
            "status_code": raw_data["status_code"],
            "elapsed_ms": raw_data["elapsed_ms"],
            "content_length": len(raw_data["content"]),
        }

        if raw_data["status_code"] not in expected_statuses:
            errors.append(
                "Unexpected status code: "
                f"{raw_data['status_code']} (expected {expected_statuses})"
            )

        min_length = validation_cfg.get("min_content_length")
        if isinstance(min_length, int) and len(raw_data["content"]) < min_length:
            errors.append(
                f"Response body too small: {len(raw_data['content'])} bytes (< {min_length})"
            )

        max_length = validation_cfg.get("max_content_length")
        if isinstance(max_length, int) and len(raw_data["content"]) > max_length:
            warnings.append(
                f"Response body large: {len(raw_data['content'])} bytes (> {max_length})"
            )

        parser = self._resolve_parser()
        soup = BeautifulSoup(raw_data["content"], parser)

        required_selectors = validation_cfg.get("required_selectors") or []
        for selector in required_selectors:
            if not soup.select(selector):
                errors.append(f"Required selector missing content: '{selector}'")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    async def transform(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Transform HTML into structured data and extracted fields."""

        transformation_cfg = self._transformation
        parser = self._resolve_parser()
        soup = BeautifulSoup(raw_data["content"], parser)

        result: dict[str, Any] = {
            "url": raw_data["url"],
            "status_code": raw_data["status_code"],
            "title": soup.title.string.strip() if soup.title and soup.title.string else None,
            "elapsed_ms": raw_data["elapsed_ms"],
        }

        if transformation_cfg.include_text:
            text = soup.get_text(
                separator=transformation_cfg.text_separator,
                strip=transformation_cfg.text_strip,
            )
            max_text_chars = transformation_cfg.max_text_chars
            if max_text_chars is not None:
                text = text[:max_text_chars]
            result["text"] = text

        if transformation_cfg.include_links:
            unique_links: dict[str, dict[str, Any]] = {}
            for anchor in soup.find_all("a", href=True):
                href_value = anchor.get("href")
                if not href_value:
                    continue
                href = str(href_value)
                text = anchor.get_text(strip=True)
                unique_links[href] = {"href": href, "text": text or None}
            result["links"] = list(unique_links.values())

        if transformation_cfg.include_metadata:
            meta_tags = []
            for meta in soup.find_all("meta"):
                attributes = {k: v for k, v in meta.attrs.items() if isinstance(v, str)}
                if attributes:
                    meta_tags.append(attributes)
            result["metadata"] = meta_tags

        if transformation_cfg.selectors:
            extracted: dict[str, Any] = {}
            for key, selector in transformation_cfg.selectors.items():
                nodes = soup.select(selector)
                extracted[key] = [node.get_text(strip=True) for node in nodes if node]
            result["extracted"] = extracted

        if transformation_cfg.include_raw:
            result["raw_html"] = raw_data["content"]

        return result

    def _resolve_parser(self) -> str:
        """Resolve the BeautifulSoup parser name from config."""

        parser = str(self.config.get("parser", self.DEFAULT_PARSER))
        if parser not in ("html.parser", "lxml", "html5lib"):
            raise TransformationError(
                "Unsupported BeautifulSoup parser. Choose from "
                "'html.parser', 'lxml', or 'html5lib'."
            )
        return parser

    def _ensure_mapping(
        self,
        value: Mapping[str, Any] | None,
        *,
        error_cls: type[Exception] = ValueError,
        context: str = "mapping",
    ) -> dict[str, Any]:
        """Return a shallow copy of mapping values, defaulting to empty dict."""

        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        raise error_cls(f"Expected mapping for {context}")

    def _parse_positive_int(self, raw_value: Any, key: str) -> int | None:
        """Convert config values to a positive integer if provided."""

        if raw_value in (None, ""):
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise CollectionError(f"{key} must be an integer") from exc
        if value <= 0:
            raise CollectionError(f"{key} must be greater than zero")
        return value

    def _parse_timeout(self, raw_value: Any) -> float:
        """Validate timeout configuration and return a float value."""

        try:
            timeout_value = float(raw_value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise CollectionError("timeout must be a numeric value") from exc

        if timeout_value <= 0:
            raise CollectionError("timeout must be greater than zero seconds")
        if timeout_value > 300:
            raise CollectionError("timeout exceeds maximum allowed value of 300 seconds")

        return timeout_value

    def _allowlist_declared(self) -> bool:
        """Return True when any host or URL pattern allowlist is configured."""

        return bool(self.config.get("allowed_hosts") or self.config.get("allowed_url_patterns"))

    def _resolve_request_url(self, url: str, base_url: str | None) -> httpx.URL:
        """Resolve and validate the absolute request URL."""

        try:
            base = httpx.URL(base_url) if base_url else None
        except (TypeError, ValueError) as exc:
            raise CollectionError(f"Invalid base_url: {exc}") from exc

        try:
            target = httpx.URL(url)
        except (TypeError, ValueError) as exc:
            raise CollectionError(f"Invalid URL: {exc}") from exc

        if target.is_relative_url:
            if base is None:
                raise CollectionError("Relative URLs require a base_url configuration")
            target = base.join(str(target))

        if target.scheme not in {"http", "https"}:
            raise CollectionError("Only HTTP(S) URLs are supported")

        return target

    def _enforce_url_allowlist(self, url: httpx.URL) -> None:
        """Ensure the resolved URL is permitted by allowlist configuration."""

        host_patterns = self._normalized_sequence("allowed_hosts")
        regex_patterns = self._compiled_patterns("allowed_url_patterns")

        if not host_patterns and not regex_patterns:
            return

        host = (url.host or "").lower()
        host_match = any(fnmatch(host, pattern) for pattern in host_patterns)
        regex_match = any(pattern.search(str(url)) for pattern in regex_patterns)

        if not host_match and not regex_match:
            raise CollectionError(
                f"URL '{url}' is not permitted by allowlist configuration"
            )

    def _enforce_network_policy(self, url: httpx.URL) -> None:
        """Block requests to private or loopback network ranges unless permitted."""

        if bool(self.config.get("allow_private_networks", False)):
            return

        host = url.host or ""
        lowered = host.lower()

        if lowered in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
            raise CollectionError("Private network hosts are disallowed by configuration")

        try:
            ip_obj = ipaddress.ip_address(lowered)
        except ValueError:
            return

        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
            raise CollectionError("Private network hosts are disallowed by configuration")

    def _normalized_sequence(self, key: str) -> list[str]:
        """Return a normalized list of non-empty lowercase strings from config."""

        raw_value = self.config.get(key)
        if raw_value is None:
            return []
        if not isinstance(raw_value, (list, tuple, set)):
            raise CollectionError(f"{key} must be a sequence of strings")

        normalized: list[str] = []
        for item in raw_value:
            if not isinstance(item, str) or not item.strip():
                raise CollectionError(f"{key} entries must be non-empty strings")
            normalized.append(item.strip().lower())
        return normalized

    def _compiled_patterns(self, key: str) -> list[re.Pattern[str]]:
        """Compile regex patterns declared in config."""

        raw_value = self.config.get(key)
        if raw_value is None:
            return []
        if not isinstance(raw_value, (list, tuple, set)):
            raise CollectionError(f"{key} must be a sequence of regex patterns")

        compiled: list[re.Pattern[str]] = []
        for pattern in raw_value:
            if not isinstance(pattern, str) or pattern.strip() == "":
                raise CollectionError(f"{key} entries must be non-empty strings")
            try:
                compiled.append(re.compile(pattern))
            except re.error as exc:
                raise CollectionError(
                    f"Invalid regex in {key}: {pattern} ({exc})"
                ) from exc
        return compiled
