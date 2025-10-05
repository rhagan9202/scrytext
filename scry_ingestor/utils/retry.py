"""Async retry utilities for HTTP-based adapters."""

from __future__ import annotations

import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
)

logger = logging.getLogger(__name__)

class RetryableStatusError(Exception):
    """Internal exception used to signal retryable HTTP status codes."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"Retryable HTTP status {response.status_code}")
        self.response = response


_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.TransportError,
    httpx.RequestError,
    RetryableStatusError,
)


class RetryConfig(BaseModel):
    """Configuration object describing HTTP retry behaviour."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_attempts: int = Field(default=3, ge=1)
    backoff_factor: float = Field(default=0.5, gt=0)
    max_backoff: float | None = Field(default=10.0, gt=0)
    jitter: float = Field(default=0.0, ge=0)
    status_forcelist: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])
    retry_on_methods: list[str] = Field(default_factory=lambda: ["GET", "HEAD", "OPTIONS"])
    respect_retry_after: bool = True

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        status_set = {int(code) for code in self.status_forcelist}
        method_set = {method.upper() for method in self.retry_on_methods}
        object.__setattr__(self, "_status_set", status_set)
        object.__setattr__(self, "_method_set", method_set)

    @field_validator("status_forcelist", mode="before")
    @classmethod
    def _coerce_status_codes(cls, value: Any) -> list[int]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("status_forcelist must be a sequence of integers")
        coerced: list[int] = []
        for item in value:
            try:
                coerced.append(int(item))
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError("status_forcelist entries must be integers") from exc
        return coerced

    @field_validator("retry_on_methods", mode="before")
    @classmethod
    def _coerce_methods(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("retry_on_methods must be a sequence of HTTP methods")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("retry_on_methods entries must be non-empty strings")
            result.append(item.strip().upper())
        return result

    def should_retry_method(self, method: str) -> bool:
        """Return True when retries are enabled for the provided HTTP method."""

        return method.upper() in getattr(self, "_method_set", set())

    def should_retry_response(self, response: httpx.Response) -> bool:
        """Return True when the HTTP response warrants a retry."""

        if response is None:
            return False
        return response.status_code in getattr(self, "_status_set", set())

    @classmethod
    def from_mapping(cls, value: Any) -> RetryConfig:
        """Parse retry configuration from a user-provided mapping."""

        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("retry configuration must be a mapping of options")
        return cls.model_validate(value)

    def describe(self) -> dict[str, Any]:
        """Return a serialisable summary useful for logging/metrics."""

        return {
            "enabled": self.enabled,
            "max_attempts": self.max_attempts,
            "backoff_factor": self.backoff_factor,
            "max_backoff": self.max_backoff,
            "jitter": self.jitter,
            "status_forcelist": list(getattr(self, "_status_set", set())),
            "retry_on_methods": list(getattr(self, "_method_set", set())),
        }


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    trimmed = value.strip()
    if trimmed == "":
        return None
    if trimmed.isdigit():
        return max(float(trimmed), 0.0)
    try:
        parsed = parsedate_to_datetime(trimmed)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delay = (parsed - now).total_seconds()
    return max(delay, 0.0)


def _wait_strategy(config: RetryConfig) -> Callable[[RetryCallState], float]:
    def _wait(retry_state: RetryCallState) -> float:
        attempt_number = max(retry_state.attempt_number, 1)
        delay = config.backoff_factor * (2 ** (attempt_number - 1))
        if config.max_backoff is not None:
            delay = min(delay, config.max_backoff)

        outcome = retry_state.outcome
        if (
            config.respect_retry_after
            and outcome is not None
            and not outcome.failed
        ):
            result = outcome.result()
            if isinstance(result, httpx.Response):
                header_value = result.headers.get("retry-after")
                header_delay = _parse_retry_after(header_value)
                if header_delay is not None:
                    delay = max(delay, header_delay)

        if config.jitter > 0:
            delay += random.uniform(0, config.jitter)
        return max(delay, 0.0)

    return _wait


def _retry_error_callback(retry_state: RetryCallState) -> httpx.Response:
    outcome = retry_state.outcome
    if outcome is None:
        raise RuntimeError("Retry attempt completed without outcome")
    if outcome.failed:
        exception = outcome.exception()
        if isinstance(exception, RetryableStatusError):
            return exception.response
        if exception is None:
            raise RuntimeError("Retry attempt raised an unknown exception")
        raise exception
    result = outcome.result()
    if isinstance(result, httpx.Response):
        return result
    raise RuntimeError("Retry attempt produced an unexpected result type")


async def execute_with_retry(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    method: str,
    retry_config: RetryConfig,
    log: logging.Logger | logging.LoggerAdapter | None = None,
) -> httpx.Response:
    """Execute an HTTP request with retries according to the provided configuration."""

    if not retry_config.enabled or retry_config.max_attempts <= 1:
        return await send()

    method_upper = method.upper()
    if not retry_config.should_retry_method(method_upper):
        return await send()

    logger_to_use = log or logger
    if isinstance(logger_to_use, logging.LoggerAdapter):
        sleep_logger = cast(logging.Logger, logger_to_use.logger)
    else:
        sleep_logger = logger_to_use

    wait_fn = _wait_strategy(retry_config)
    retry_policy = retry_if_exception_type(_RETRYABLE_EXCEPTIONS)

    response: httpx.Response | None = None
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(retry_config.max_attempts),
        wait=wait_fn,
        retry=retry_policy,
        before_sleep=before_sleep_log(sleep_logger, logging.WARNING),
        reraise=False,
        retry_error_callback=_retry_error_callback,
    ):
        with attempt:
            response = await send()
            if retry_config.should_retry_response(response):
                raise RetryableStatusError(response)

    if response is None:  # pragma: no cover - defensive
        raise RuntimeError("Retry loop exited without producing a response")

    return response
