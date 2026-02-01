"""Tests for rate limiting middleware."""

import time

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from scry_ingestor.api.rate_limit import (
    RateLimiter,
    RateLimitMiddleware,
    create_rate_limit_middleware,
)


class TestRateLimiter:
    """Test token bucket rate limiter."""

    def test_initial_request_allowed(self):
        """Test that first request is always allowed."""
        limiter = RateLimiter(requests_per_window=10, window_seconds=60)
        allowed, metadata = limiter.is_allowed("test_key")

        assert allowed is True
        assert metadata["limit"] == 10
        assert metadata["remaining"] >= 0

    def test_rate_limit_exceeded(self):
        """Test that requests are blocked after exceeding limit."""
        limiter = RateLimiter(requests_per_window=3, window_seconds=60, burst_size=3)

        for i in range(3):
            allowed, _ = limiter.is_allowed("test_key")
            assert allowed is True, f"Request {i+1} should be allowed"

        allowed, metadata = limiter.is_allowed("test_key")
        assert allowed is False
        assert metadata["remaining"] == 0

    def test_token_refill_over_time(self):
        """Test that tokens refill over time."""
        limiter = RateLimiter(requests_per_window=10, window_seconds=1, burst_size=10)

        for _ in range(10):
            limiter.is_allowed("test_key")

        allowed, _ = limiter.is_allowed("test_key")
        assert allowed is False

        time.sleep(0.2)

        allowed1, _ = limiter.is_allowed("test_key")
        allowed2, _ = limiter.is_allowed("test_key")
        allowed3, _ = limiter.is_allowed("test_key")

        assert allowed1 is True
        assert allowed2 is True
        assert allowed3 is False

    def test_burst_size(self):
        """Test burst size limits maximum tokens."""
        limiter = RateLimiter(requests_per_window=100, window_seconds=60, burst_size=5)

        for i in range(5):
            allowed, _ = limiter.is_allowed("test_key")
            assert allowed is True, f"Request {i+1} should be allowed"

        allowed, _ = limiter.is_allowed("test_key")
        assert allowed is False

    def test_different_keys_independent(self):
        """Test that different keys have independent rate limits."""
        limiter = RateLimiter(requests_per_window=2, window_seconds=60)

        limiter.is_allowed("key1")
        limiter.is_allowed("key1")
        allowed_key1, _ = limiter.is_allowed("key1")

        allowed_key2, _ = limiter.is_allowed("key2")

        assert allowed_key1 is False
        assert allowed_key2 is True

    def test_cleanup_stale_buckets(self):
        """Test cleanup of stale rate limit entries."""
        limiter = RateLimiter(requests_per_window=10, window_seconds=60)

        limiter.is_allowed("key1")
        limiter.is_allowed("key2")
        limiter.is_allowed("key3")

        assert len(limiter._buckets) == 3

        old_time = time.time() - 7200
        limiter._buckets["key1"] = (10.0, old_time)

        limiter.cleanup_stale_buckets(max_age_seconds=3600)

        assert len(limiter._buckets) == 2
        assert "key1" not in limiter._buckets
        assert "key2" in limiter._buckets
        assert "key3" in limiter._buckets

    def test_reset_timestamp(self):
        """Test that reset timestamp is calculated correctly."""
        limiter = RateLimiter(requests_per_window=10, window_seconds=60)

        allowed, metadata = limiter.is_allowed("test_key")
        reset_time = metadata["reset"]

        assert reset_time > time.time()

        time_until_reset = reset_time - time.time()
        assert 50 < time_until_reset < 70


@pytest.mark.asyncio
class TestRateLimitMiddleware:
    """Test FastAPI rate limit middleware."""

    def create_test_app(self, **middleware_kwargs):
        """Helper to create FastAPI app with rate limit middleware."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, **middleware_kwargs)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.get("/health")
        async def health_endpoint():
            return {"status": "ok"}

        return app

    async def test_rate_limit_headers_added(self):
        """Test that rate limit headers are added to responses."""
        app = self.create_test_app(
            enabled=True, requests_per_window=10, window_seconds=60
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "10"

    async def test_rate_limit_enforcement(self):
        """Test that rate limit is enforced."""
        app = self.create_test_app(
            enabled=True, requests_per_window=3, window_seconds=60, burst_size=3
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            for i in range(3):
                response = await client.get("/test")
                assert response.status_code == 200, f"Request {i+1} should succeed"

            response = await client.get("/test")

        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]

    async def test_exempt_paths(self):
        """Test that exempt paths are not rate limited."""
        app = self.create_test_app(
            enabled=True,
            requests_per_window=2,
            window_seconds=60,
            exempt_paths=["/health"],
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            await client.get("/test")
            await client.get("/test")
            response = await client.get("/test")
            assert response.status_code == 429

            response = await client.get("/health")

        assert response.status_code == 200

    async def test_disabled_rate_limiting(self):
        """Test that rate limiting can be disabled."""
        app = self.create_test_app(
            enabled=False, requests_per_window=1, window_seconds=60
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            for _ in range(10):
                response = await client.get("/test")
                assert response.status_code == 200

    async def test_rate_limit_by_ip(self):
        """Test rate limiting by IP address."""
        app = self.create_test_app(
            enabled=True,
            requests_per_window=2,
            window_seconds=60,
            limit_by="ip",
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            await client.get("/test")
            await client.get("/test")
            response = await client.get("/test")

        assert response.status_code == 429

    async def test_rate_limit_by_api_key(self):
        """Test rate limiting by API key."""
        app = self.create_test_app(
            enabled=True,
            requests_per_window=2,
            window_seconds=60,
            limit_by="api_key",
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            await client.get("/test", headers={"X-API-Key": "api_key_1"})
            await client.get("/test", headers={"X-API-Key": "api_key_1"})
            response = await client.get("/test", headers={"X-API-Key": "api_key_1"})
            assert response.status_code == 429

            response = await client.get("/test", headers={"X-API-Key": "api_key_2"})

        assert response.status_code == 200

    async def test_rate_limit_by_endpoint(self):
        """Test rate limiting by endpoint path."""
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            enabled=True,
            requests_per_window=2,
            window_seconds=60,
            limit_by="endpoint",
        )

        @app.get("/endpoint1")
        async def endpoint1():
            return {"message": "endpoint1"}

        @app.get("/endpoint2")
        async def endpoint2():
            return {"message": "endpoint2"}

        async with AsyncClient(app=app, base_url="http://test") as client:
            await client.get("/endpoint1")
            await client.get("/endpoint1")
            response = await client.get("/endpoint1")
            assert response.status_code == 429

            response = await client.get("/endpoint2")

        assert response.status_code == 200

    async def test_x_forwarded_for_header(self):
        """Test that X-Forwarded-For header is respected for IP limiting."""
        app = self.create_test_app(
            enabled=True, requests_per_window=2, window_seconds=60, limit_by="ip"
        )
        async with AsyncClient(app=app, base_url="http://test") as client:
            headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.1"}

            await client.get("/test", headers=headers)
            await client.get("/test", headers=headers)
            response = await client.get("/test", headers=headers)

        assert response.status_code == 429

    async def test_factory_function(self):
        """Test create_rate_limit_middleware factory function."""
        middleware_class = create_rate_limit_middleware(
            enabled=True,
            requests_per_window=5,
            window_seconds=30,
            limit_by="ip",
        )

        app = FastAPI()
        app.add_middleware(middleware_class)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "5"
