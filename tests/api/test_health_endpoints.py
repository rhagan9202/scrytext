"""Tests for health check API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from scry_ingestor.api.main import app
from scry_ingestor.utils.health import ComponentHealth, HealthStatus, get_health_checker


@pytest.fixture(autouse=True)
def reset_health_checker():
    """Reset health checker before each test."""
    from scry_ingestor.utils import health

    health._health_checker = None
    yield
    health._health_checker = None


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test basic health check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "service" in data
    assert "checked_at" in data


@pytest.mark.asyncio
async def test_readiness_endpoint():
    """Test readiness check endpoint."""
    # Register mock health checks
    checker = get_health_checker()

    def mock_db_check() -> ComponentHealth:
        return ComponentHealth(name="database", status=HealthStatus.HEALTHY)

    def mock_redis_check() -> ComponentHealth:
        return ComponentHealth(name="redis", status=HealthStatus.HEALTHY)

    def mock_celery_check() -> ComponentHealth:
        return ComponentHealth(name="celery", status=HealthStatus.HEALTHY)

    def mock_kafka_check() -> ComponentHealth:
        return ComponentHealth(name="kafka", status=HealthStatus.HEALTHY)

    checker.register_check("database", mock_db_check)
    checker.register_check("redis", mock_redis_check)
    checker.register_check("celery", mock_celery_check)
    checker.register_check("kafka", mock_kafka_check)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "scry_ingestor"
    assert "components" in data


@pytest.mark.asyncio
async def test_readiness_endpoint_with_detailed():
    """Test readiness endpoint with detailed flag."""
    # Register mock health checks
    checker = get_health_checker()

    def mock_db_check() -> ComponentHealth:
        return ComponentHealth(
            name="database", status=HealthStatus.HEALTHY, message="Connection OK"
        )

    checker.register_check("database", mock_db_check)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ready?detailed=true")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert len(data["components"]) > 0
    assert "database" in data["components"]


@pytest.mark.asyncio
async def test_detailed_health_endpoint():
    """Test detailed health check endpoint."""
    # Register mock health checks
    checker = get_health_checker()

    def mock_api_check() -> ComponentHealth:
        return ComponentHealth(
            name="api",
            status=HealthStatus.HEALTHY,
            message="API running",
            metadata={"version": "1.0.0"},
        )

    checker.register_check("api", mock_api_check)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "service" in data
    assert "version" in data
    assert "uptime_seconds" in data
    assert "components" in data
    assert len(data["components"]) > 0


@pytest.mark.asyncio
async def test_readiness_degraded_component():
    """Test readiness when a component is degraded."""
    checker = get_health_checker()

    def mock_degraded_check() -> ComponentHealth:
        return ComponentHealth(name="kafka", status=HealthStatus.DEGRADED)

    def mock_healthy_check() -> ComponentHealth:
        return ComponentHealth(name="database", status=HealthStatus.HEALTHY)

    checker.register_check("kafka", mock_degraded_check)
    checker.register_check("database", mock_healthy_check)
    checker.register_check("redis", mock_healthy_check)
    checker.register_check("celery", mock_healthy_check)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_readiness_unhealthy_component():
    """Test readiness when a required component is unhealthy."""
    checker = get_health_checker()

    def mock_unhealthy_check() -> ComponentHealth:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message="Connection failed",
        )

    def mock_healthy_check() -> ComponentHealth:
        return ComponentHealth(name="healthy", status=HealthStatus.HEALTHY)

    checker.register_check("database", mock_unhealthy_check)
    checker.register_check("redis", mock_healthy_check)
    checker.register_check("celery", mock_healthy_check)
    checker.register_check("kafka", mock_healthy_check)

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unhealthy"
