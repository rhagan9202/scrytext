"""Rate limiting middleware for FastAPI API endpoints."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..utils.logging import setup_logger

logger = setup_logger(__name__, context={"middleware": "rate_limit"})


class RateLimiter:
    """
    Token bucket rate limiter.

    Implements a token bucket algorithm for rate limiting with configurable
    limits per time window. Supports different limit keys (IP, API key, endpoint).
    """

    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_size: int | None = None,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_window: Maximum requests allowed per time window
            window_seconds: Time window duration in seconds
            burst_size: Maximum burst size (defaults to requests_per_window)
        """
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.burst_size = burst_size or requests_per_window

        # Token bucket state: {key: (tokens, last_refill_time)}
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (float(self.burst_size), time.time())
        )

        # Rate of token refill per second
        self._refill_rate = self.requests_per_window / self.window_seconds

    def _refill_bucket(self, key: str, current_time: float) -> float:
        """
        Refill tokens in bucket based on elapsed time.

        Args:
            key: Rate limit key
            current_time: Current timestamp

        Returns:
            Current token count after refill
        """
        tokens, last_refill = self._buckets[key]

        # Calculate tokens to add based on elapsed time
        elapsed = current_time - last_refill
        new_tokens = tokens + (elapsed * self._refill_rate)

        # Cap at burst size
        new_tokens = min(new_tokens, self.burst_size)

        # Update bucket
        self._buckets[key] = (new_tokens, current_time)

        return new_tokens

    def is_allowed(self, key: str) -> tuple[bool, dict[str, int]]:  # type: ignore[return]
        """
        Check if request is allowed under rate limit.

        Args:
            key: Rate limit key (e.g., IP address, API key)

        Returns:
            Tuple of (allowed, metadata) where metadata contains:
            - limit: Maximum requests per window
            - remaining: Remaining requests in current window
            - reset: Unix timestamp when limit resets
        """
        current_time = time.time()

        # Refill tokens
        tokens = self._refill_bucket(key, current_time)

        # Check if we have at least 1 token
        if tokens >= 1.0:
            # Consume 1 token
            self._buckets[key] = (tokens - 1.0, current_time)
            allowed = True
        else:
            allowed = False

        # Calculate reset time (when bucket will have 1+ tokens)
        tokens_after_consume = tokens - 1.0 if allowed else tokens
        if tokens_after_consume < 0:
            # Calculate time until next token
            time_to_next_token = abs(tokens_after_consume) / self._refill_rate
            reset_time = current_time + time_to_next_token
        else:
            reset_time = current_time + self.window_seconds

        metadata = {
            "limit": self.requests_per_window,
            "remaining": int(max(0, tokens_after_consume)),
            "reset": int(reset_time),
        }

        return allowed, metadata

    def cleanup_stale_buckets(self, max_age_seconds: int = 3600) -> None:
        """
        Remove stale rate limit entries.

        Args:
            max_age_seconds: Remove buckets not accessed in this many seconds
        """
        current_time = time.time()
        stale_keys = [
            key
            for key, (_, last_refill) in self._buckets.items()
            if current_time - last_refill > max_age_seconds
        ]

        for key in stale_keys:
            del self._buckets[key]

        if stale_keys:
            logger.debug(
                f"Cleaned up {len(stale_keys)} stale rate limit buckets",
                extra={"status": "info", "stale_count": len(stale_keys)},
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Supports multiple rate limit strategies:
    - By IP address (default)
    - By API key (from X-API-Key header)
    - By endpoint path

    Returns 429 (Too Many Requests) when limit is exceeded.
    Adds rate limit headers to all responses:
    - X-RateLimit-Limit: Maximum requests per window
    - X-RateLimit-Remaining: Remaining requests in window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    """

    def __init__(
        self,
        app,
        *,
        enabled: bool = True,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        burst_size: int | None = None,
        limit_by: str = "ip",  # "ip", "api_key", or "endpoint"
        exempt_paths: list[str] | None = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            enabled: Whether rate limiting is enabled
            requests_per_window: Maximum requests per time window
            window_seconds: Time window in seconds
            burst_size: Maximum burst size
            limit_by: Rate limit key strategy ("ip", "api_key", "endpoint")
            exempt_paths: List of paths to exempt from rate limiting
        """
        super().__init__(app)
        self.enabled = enabled
        self.limit_by = limit_by
        self.exempt_paths = exempt_paths or ["/health", "/ready", "/docs", "/openapi.json"]

        self.limiter = RateLimiter(
            requests_per_window=requests_per_window,
            window_seconds=window_seconds,
            burst_size=burst_size,
        )

        logger.info(
            f"Rate limiting initialized: {requests_per_window} req/{window_seconds}s "
            f"(by {limit_by}, enabled={enabled})",
            extra={
                "status": "info",
                "limit": requests_per_window,
                "window": window_seconds,
                "strategy": limit_by,
            },
        )

    def _get_rate_limit_key(self, request: Request) -> str:
        """
        Extract rate limit key from request.

        Args:
            request: FastAPI request

        Returns:
            Rate limit key string
        """
        if self.limit_by == "api_key":
            # Use API key from header
            api_key = request.headers.get("X-API-Key", "")
            if api_key:
                return f"api_key:{api_key}"
            # Fall back to IP if no API key
            client_host = request.client.host if request.client else "unknown"
            return f"ip:{client_host}"

        elif self.limit_by == "endpoint":
            # Use endpoint path
            return f"endpoint:{request.url.path}"

        else:  # "ip" (default)
            # Use client IP address
            # Check for X-Forwarded-For header (proxy/load balancer)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Take first IP in chain
                client_ip = forwarded_for.split(",")[0].strip()
            else:
                client_ip = request.client.host if request.client else "unknown"

            return f"ip:{client_ip}"

    def _is_exempt(self, path: str) -> bool:
        """
        Check if path is exempt from rate limiting.

        Args:
            path: Request path

        Returns:
            True if exempt, False otherwise
        """
        return any(path.startswith(exempt_path) for exempt_path in self.exempt_paths)

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request through rate limiting middleware.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response (either from handler or 429 error)
        """
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip exempt paths
        if self._is_exempt(request.url.path):
            return await call_next(request)

        # Get rate limit key
        limit_key = self._get_rate_limit_key(request)

        # Check rate limit
        allowed, metadata = self.limiter.is_allowed(limit_key)

        # Add rate limit headers
        headers = {
            "X-RateLimit-Limit": str(metadata["limit"]),
            "X-RateLimit-Remaining": str(metadata["remaining"]),
            "X-RateLimit-Reset": str(metadata["reset"]),
        }

        if not allowed:
            # Rate limit exceeded
            logger.warning(
                f"Rate limit exceeded for {limit_key}",
                extra={
                    "status": "rate_limited",
                    "key": limit_key,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": metadata["limit"],
                    "reset": metadata["reset"],
                },
                headers=headers,
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to successful response
        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value

        return response


def create_rate_limit_middleware(
    *,
    enabled: bool = True,
    requests_per_window: int = 100,
    window_seconds: int = 60,
    burst_size: int | None = None,
    limit_by: str = "ip",
    exempt_paths: list[str] | None = None,
) -> type[RateLimitMiddleware]:
    """
    Factory function to create rate limit middleware with specific configuration.

    Args:
        enabled: Whether rate limiting is enabled
        requests_per_window: Maximum requests per time window
        window_seconds: Time window in seconds
        burst_size: Maximum burst size
        limit_by: Rate limit key strategy
        exempt_paths: Paths exempt from rate limiting

    Returns:
        Configured RateLimitMiddleware class
    """

    class ConfiguredRateLimitMiddleware(RateLimitMiddleware):
        def __init__(self, app):
            super().__init__(
                app,
                enabled=enabled,
                requests_per_window=requests_per_window,
                window_seconds=window_seconds,
                burst_size=burst_size,
                limit_by=limit_by,
                exempt_paths=exempt_paths,
            )

    return ConfiguredRateLimitMiddleware
