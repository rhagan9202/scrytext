"""Adapter for interacting with RESTful web APIs."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from asyncio import Lock
from collections.abc import Mapping
from copy import deepcopy
from fnmatch import fnmatch
from typing import Any

import httpx
from cachetools import TTLCache
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError as PydanticValidationError,
    field_validator,
)

from ..exceptions import CollectionError, ConfigurationError, TransformationError, ValidationError
from ..schemas.payload import ValidationResult
from ..schemas.transformations import RESTTransformationConfig
from ..utils.logging import setup_logger
from ..utils.retry import RetryConfig, execute_with_retry
from .base import BaseAdapter


class RESTCacheConfig(BaseModel):
    """Runtime cache configuration for RESTAdapter responses."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    ttl_seconds: float = Field(default=60.0, gt=0)
    max_size: int = Field(default=256, ge=1)
    methods: set[str] = Field(default_factory=lambda: {"GET"})
    vary_headers: list[str] = Field(default_factory=list)

    @field_validator("methods", mode="before")
    @classmethod
    def _coerce_methods(cls, value: Any) -> set[str]:
        if value is None:
            return {"GET"}
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (list, tuple, set)):
            normalized = {str(item).upper() for item in value if str(item).strip()}
            if not normalized:
                raise ValueError("cache.methods must declare at least one HTTP method")
            return normalized
        raise ValueError("cache.methods must be a string or sequence of strings")

    @field_validator("vary_headers", mode="before")
    @classmethod
    def _coerce_vary_headers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (list, tuple, set)):
            result: list[str] = []
            for header in value:
                if not isinstance(header, str) or not header.strip():
                    raise ValueError("cache.vary_headers entries must be non-empty strings")
                result.append(header.strip().lower())
            return result
        raise ValueError("cache.vary_headers must be a string or sequence of strings")


class RESTAdapter(BaseAdapter):
    """Adapter that fetches data from HTTP APIs using httpx."""

    SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    logger = setup_logger(__name__, context={"adapter_type": "RESTAdapter"})

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            self._transformation = RESTTransformationConfig.model_validate(
                config.get("transformation") or {}
            )
        except PydanticValidationError as exc:
            raise ConfigurationError(
                f"Invalid REST transformation configuration: {exc}"
            ) from exc
        try:
            self._retry_config = RetryConfig.from_mapping(config.get("retry"))
        except (PydanticValidationError, ValueError) as exc:
            raise ConfigurationError(f"Invalid retry configuration: {exc}") from exc
        try:
            self._cache_config = RESTCacheConfig.model_validate(config.get("cache") or {})
        except PydanticValidationError as exc:
            raise ConfigurationError(f"Invalid cache configuration: {exc}") from exc

        invalid_methods = self._cache_config.methods - self.SUPPORTED_METHODS
        if invalid_methods:
            raise ConfigurationError(
                "Cache configuration references unsupported HTTP methods: "
                f"{sorted(invalid_methods)}"
            )

        self._cache_store: TTLCache[tuple[Any, ...], dict[str, Any]] | None = None
        self._cache_lock: Lock | None = None
        if self._cache_config.enabled:
            self._cache_store = TTLCache(
                maxsize=self._cache_config.max_size,
                ttl=self._cache_config.ttl_seconds,
            )
            self._cache_lock = Lock()

    async def collect(self) -> dict[str, Any]:
        """Perform the HTTP request and return the raw response payload."""

        method = (self.config.get("method") or "GET").upper()
        if method not in self.SUPPORTED_METHODS:
            raise CollectionError(f"Unsupported HTTP method: {method}")

        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise CollectionError("REST adapter requires an 'endpoint' URL in the config")

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
        headers = self._ensure_dict(
            self.config.get("headers"),
            error_cls=CollectionError,
            context="headers configuration",
        )
        params = self._ensure_dict(
            self.config.get("query_params"),
            error_cls=CollectionError,
            context="query parameter configuration",
        )
        body = self.config.get("body")
        response_format = self._response_format_hint()
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

        target_url = self._resolve_request_url(endpoint, base_url)
        self._enforce_url_allowlist(target_url)
        self._enforce_network_policy(target_url)

        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "params": params,
        }

        auth_config = self._ensure_dict(
            self.config.get("auth"),
            error_cls=CollectionError,
            context="auth configuration",
        )
        auth = None
        auth_type = str(auth_config.get("type", "none")).lower()
        if auth_type == "basic":
            username = auth_config.get("username")
            password = auth_config.get("password")
            if username is None or password is None:
                raise CollectionError("Basic auth requires both username and password")
            auth = (username, password)
        elif auth_type == "bearer":
            token = auth_config.get("token")
            if not token:
                raise CollectionError("Bearer auth requires a token")
            headers.setdefault("Authorization", f"Bearer {token}")
        elif auth_type not in ("none", ""):
            raise CollectionError(f"Unsupported auth type: {auth_type}")

        if auth is not None:
            request_kwargs["auth"] = auth

        if body is not None:
            if isinstance(body, dict | list):
                request_kwargs["json"] = body
            else:
                body_format = self.config.get("body_format", "auto").lower()
                if body_format == "json" and isinstance(body, str):
                    request_kwargs["json"] = json.loads(body)
                else:
                    request_kwargs["content"] = (
                        body if isinstance(body, bytes | bytearray) else str(body)
                    )

        cache_key: tuple[Any, ...] | None = None
        if self._cache_enabled_for_method(method):
            cache_key = self._build_cache_key(
                method=method,
                url=str(target_url),
                params=params,
                headers=headers,
                request_kwargs=request_kwargs,
            )
            cached_response = await self._get_cached_response(cache_key)
            if cached_response is not None:
                return cached_response

        retry_config = self._retry_config

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                async def _send() -> httpx.Response:
                    return await client.request(method, endpoint, **request_kwargs)

                response = await execute_with_retry(
                    _send,
                    method=method,
                    retry_config=retry_config,
                    log=self.logger,
                )
        except httpx.TimeoutException as exc:
            raise CollectionError(f"HTTP request timed out after {timeout} seconds") from exc
        except httpx.HTTPError as exc:
            raise CollectionError(f"HTTP request failed: {exc}") from exc

        await response.aread()

        self._enforce_url_allowlist(response.request.url)
        self._enforce_network_policy(response.request.url)

        if not follow_redirects and response.is_redirect:
            raise CollectionError(
                "Redirect responses are disallowed by configuration"
            )

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

        raw_response = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": response.content,
            "text": response.text,
            "response_format_hint": response_format,
            "elapsed_ms": elapsed_ms,
            "url": str(response.request.url),
            "request": {
                "method": method,
                "headers": dict(response.request.headers),
                "params": params,
                "body": request_kwargs.get("json", request_kwargs.get("content")),
            },
        }

        if cache_key is not None:
            await self._store_cached_response(cache_key, raw_response)

        return raw_response

    def _cache_enabled_for_method(self, method: str) -> bool:
        """Return True when caching is active for the given HTTP method."""

        return self._cache_store is not None and method in self._cache_config.methods

    async def _get_cached_response(
        self,
        cache_key: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        """Retrieve a cached response when present."""

        if self._cache_store is None or self._cache_lock is None:
            return None
        async with self._cache_lock:
            cached = self._cache_store.get(cache_key)
        if cached is None:
            return None
        return deepcopy(cached)

    async def _store_cached_response(
        self,
        cache_key: tuple[Any, ...],
        payload: dict[str, Any],
    ) -> None:
        """Persist a response payload in the cache."""

        if self._cache_store is None or self._cache_lock is None:
            return
        async with self._cache_lock:
            self._cache_store[cache_key] = deepcopy(payload)

    def _build_cache_key(
        self,
        *,
        method: str,
        url: str,
        params: Mapping[str, Any],
        headers: Mapping[str, Any],
        request_kwargs: Mapping[str, Any],
    ) -> tuple[Any, ...]:
        """Construct a stable cache key for the HTTP request."""

        param_items = tuple(
            sorted((str(key), self._stringify_param_value(value)) for key, value in params.items())
        )

        header_lookup = {str(key).lower(): str(value) for key, value in headers.items()}
        header_items = tuple(
            (header, header_lookup.get(header, ""))
            for header in self._cache_config.vary_headers
        )

        body_digest = self._digest_request_body(request_kwargs)

        return method, url, param_items, header_items, body_digest

    @staticmethod
    def _stringify_param_value(value: Any) -> str:
        """Normalize query parameter values for cache keys."""

        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item) for item in value)
        return str(value)

    def _digest_request_body(self, request_kwargs: Mapping[str, Any]) -> str | None:
        """Generate a stable digest for request body content."""

        if "json" in request_kwargs:
            try:
                normalized = json.dumps(
                    request_kwargs["json"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError):  # pragma: no cover - fallback for non-serializable data
                normalized = repr(request_kwargs["json"])
            return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        content = request_kwargs.get("content")
        if content is None:
            return None
        if isinstance(content, (bytes, bytearray)):
            body_bytes = bytes(content)
        else:
            body_bytes = str(content).encode("utf-8")
        return hashlib.sha256(body_bytes).hexdigest()

    async def validate(self, raw_data: dict[str, Any]) -> ValidationResult:
        """Validate response status code and basic constraints."""

        validation_cfg = self._ensure_dict(
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

        required_headers = validation_cfg.get("required_headers") or []
        missing_headers = [h for h in required_headers if h not in raw_data["headers"]]
        if missing_headers:
            errors.append(f"Missing required headers: {missing_headers}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    async def transform(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Transform the HTTP response content into structured data."""

        transformation_cfg = self._transformation
        preferred_format = transformation_cfg.response_format

        body: Any
        try:
            body = self._parse_body(raw_data, preferred_format)
        except ValueError as exc:
            raise TransformationError(str(exc)) from exc

        result: dict[str, Any] = {
            "status_code": raw_data["status_code"],
            "headers": raw_data["headers"],
            "elapsed_ms": raw_data["elapsed_ms"],
            "url": raw_data["url"],
            "body": body,
        }

        request_info = raw_data.get("request", {})
        if request_info:
            result["request"] = request_info

        return result

    def _parse_body(self, raw_data: dict[str, Any], preferred_format: str) -> Any:
        """Decode response content into the desired representation."""

        content_type = (raw_data["headers"].get("content-type") or "").lower()
        content = raw_data["content"]
        text = raw_data["text"]

        chosen_format = preferred_format
        if preferred_format == "auto":
            if "json" in content_type:
                chosen_format = "json"
            elif "text" in content_type or content_type == "":
                chosen_format = "text"
            else:
                chosen_format = "bytes"

        if chosen_format == "json":
            try:
                return json.loads(text)
            except ValueError as exc:  # pragma: no cover - defensive branch
                raise ValueError("Failed to parse JSON response body") from exc
        if chosen_format == "text":
            return text
        if chosen_format == "bytes":
            return content

        raise ValueError(f"Unsupported response_format: {preferred_format}")

    def _ensure_dict(
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

    def _response_format_hint(self) -> str:
        """Return the preferred response format hint from config."""
        return self._transformation.response_format

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

    def _allowlist_declared(self) -> bool:
        """Return True when any host or URL pattern allowlist is configured."""

        return bool(self.config.get("allowed_hosts") or self.config.get("allowed_url_patterns"))

    def _resolve_request_url(self, endpoint: str, base_url: str | None) -> httpx.URL:
        """Resolve the final request URL for validation purposes."""

        try:
            base = httpx.URL(base_url) if base_url else None
        except (TypeError, ValueError) as exc:
            raise CollectionError(f"Invalid base_url: {exc}") from exc

        try:
            target = httpx.URL(endpoint)
        except (TypeError, ValueError) as exc:
            raise CollectionError(f"Invalid endpoint URL: {exc}") from exc

        if target.is_relative_url:
            if base is None:
                raise CollectionError("Relative endpoints require a base_url configuration")
            target = base.join(str(target))

        if target.scheme not in {"http", "https"}:
            raise CollectionError("Only HTTP(S) endpoints are supported")

        return target

    def _enforce_url_allowlist(self, url: httpx.URL) -> None:
        """Raise if resolved URL is not allowed by allowlist configuration."""

        host_patterns = self._normalized_sequence("allowed_hosts")
        regex_patterns = self._compiled_patterns("allowed_url_patterns")

        if not host_patterns and not regex_patterns:
            return

        host = (url.host or "").lower()
        host_match = any(fnmatch(host, pattern) for pattern in host_patterns)
        regex_match = any(pattern.search(str(url)) for pattern in regex_patterns)

        if not host_match and not regex_match:
            raise CollectionError(
                f"Endpoint '{url}' is not permitted by allowlist configuration"
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
        if not isinstance(raw_value, list | tuple | set):
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
        if not isinstance(raw_value, list | tuple | set):
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
