"""Tests for health checking utilities."""

from __future__ import annotations

import pytest

from scry_ingestor.utils.health import (
    ComponentHealth,
    HealthChecker,
    HealthStatus,
    get_health_checker,
)


@pytest.mark.asyncio
async def test_component_health_creation():
    """Test ComponentHealth model creation."""
    health = ComponentHealth(
        name="test_component",
        status=HealthStatus.HEALTHY,
        message="All systems operational",
    )

    assert health.name == "test_component"
    assert health.status == HealthStatus.HEALTHY
    assert health.message == "All systems operational"
    assert health.checked_at is not None
    assert isinstance(health.metadata, dict)


@pytest.mark.asyncio
async def test_health_checker_registration():
    """Test registering health checks."""
    checker = HealthChecker()

    def mock_check() -> ComponentHealth:
        return ComponentHealth(
            name="mock",
            status=HealthStatus.HEALTHY,
        )

    checker.register_check("mock", mock_check)
    assert "mock" in checker._checks


@pytest.mark.asyncio
async def test_health_checker_component_check():
    """Test checking individual component health."""
    checker = HealthChecker()

    def healthy_check() -> ComponentHealth:
        return ComponentHealth(name="test", status=HealthStatus.HEALTHY)

    checker.register_check("test", healthy_check)
    result = await checker.check_component("test")

    assert result.name == "test"
    assert result.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_health_checker_async_check():
    """Test async health check function."""
    checker = HealthChecker()

    async def async_check() -> ComponentHealth:
        return ComponentHealth(name="async_test", status=HealthStatus.HEALTHY)

    checker.register_check("async_test", async_check)
    result = await checker.check_component("async_test")

    assert result.name == "async_test"
    assert result.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_health_checker_failing_check():
    """Test handling of failing health checks."""
    checker = HealthChecker()

    def failing_check() -> ComponentHealth:
        raise RuntimeError("Check failed")

    checker.register_check("failing", failing_check)
    result = await checker.check_component("failing")

    assert result.name == "failing"
    assert result.status == HealthStatus.UNHEALTHY
    assert "failed" in result.message.lower()


@pytest.mark.asyncio
async def test_health_checker_check_all():
    """Test checking all components."""
    checker = HealthChecker()

    def healthy_check() -> ComponentHealth:
        return ComponentHealth(name="healthy", status=HealthStatus.HEALTHY)

    def degraded_check() -> ComponentHealth:
        return ComponentHealth(name="degraded", status=HealthStatus.DEGRADED)

    checker.register_check("healthy", healthy_check)
    checker.register_check("degraded", degraded_check)

    system_health = await checker.check_all()

    assert system_health.status == HealthStatus.DEGRADED  # One degraded means overall degraded
    assert "healthy" in system_health.components
    assert "degraded" in system_health.components
    assert system_health.uptime_seconds is not None


@pytest.mark.asyncio
async def test_health_checker_required_components():
    """Test required components filtering."""
    checker = HealthChecker()

    def healthy_check() -> ComponentHealth:
        return ComponentHealth(name="healthy", status=HealthStatus.HEALTHY)

    def unhealthy_check() -> ComponentHealth:
        return ComponentHealth(name="unhealthy", status=HealthStatus.UNHEALTHY)

    checker.register_check("healthy", healthy_check)
    checker.register_check("unhealthy", unhealthy_check)

    # Only require healthy component
    system_health = await checker.check_all(required_components=["healthy"])
    assert system_health.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_health_checker_timeout():
    """Test health check timeout handling."""
    checker = HealthChecker()

    async def slow_check() -> ComponentHealth:
        import asyncio

        await asyncio.sleep(10)  # Longer than timeout
        return ComponentHealth(name="slow", status=HealthStatus.HEALTHY)

    checker.register_check("slow", slow_check)

    system_health = await checker.check_all(timeout=0.1)

    assert system_health.components["slow"].status == HealthStatus.UNHEALTHY
    assert "timed out" in system_health.components["slow"].message.lower()


@pytest.mark.asyncio
async def test_get_health_checker_singleton():
    """Test global health checker singleton."""
    checker1 = get_health_checker()
    checker2 = get_health_checker()

    assert checker1 is checker2


@pytest.mark.asyncio
async def test_health_status_enum():
    """Test HealthStatus enum values."""
    assert HealthStatus.HEALTHY.value == "healthy"
    assert HealthStatus.DEGRADED.value == "degraded"
    assert HealthStatus.UNHEALTHY.value == "unhealthy"


@pytest.mark.asyncio
async def test_system_health_model():
    """Test SystemHealth model."""
    from scry_ingestor.utils.health import SystemHealth

    system_health = SystemHealth(
        status=HealthStatus.HEALTHY,
        service="test_service",
        version="1.0.0",
    )

    assert system_health.status == HealthStatus.HEALTHY
    assert system_health.service == "test_service"
    assert system_health.version == "1.0.0"
    assert isinstance(system_health.components, dict)
