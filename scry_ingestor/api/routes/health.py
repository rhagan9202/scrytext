"""Health check and readiness endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ...utils.health import SystemHealth, get_health_checker
from ...utils.health_checks import register_all_health_checks

router = APIRouter()

# Register health checks on module import
register_all_health_checks()


@router.get("/health", summary="Health check (liveness probe)")
async def health_check() -> dict[str, Any]:
    """
    Basic health check endpoint (liveness probe).

    Returns the minimal health status indicating the service is alive.
    This endpoint checks only critical components and returns quickly.

    Use this for Kubernetes liveness probes or basic monitoring.

    Returns:
        dict: Simple health status with service name and status
    """
    checker = get_health_checker()

    # Check only critical components for liveness
    system_health = await checker.check_all(
        timeout=3.0, required_components=["api"]  # Only API must be running for liveness
    )

    return {
        "status": system_health.status.value,
        "service": system_health.service,
        "checked_at": system_health.checked_at.isoformat(),
    }


@router.get(
    "/ready",
    summary="Readiness check (readiness probe)",
    response_model=SystemHealth,
)
async def readiness_check(
    detailed: bool = Query(
        False, description="Include detailed component status information"
    ),
) -> SystemHealth:
    """
    Readiness check endpoint (readiness probe).

    Checks if the service is ready to accept traffic by verifying all
    critical dependencies are available: database, Redis, Celery, and Kafka.

    Use this for Kubernetes readiness probes or load balancer health checks.

    Args:
        detailed: If True, includes detailed status for each component

    Returns:
        SystemHealth: Comprehensive readiness status with component details
    """
    checker = get_health_checker()

    # Check all critical components for readiness
    system_health = await checker.check_all(
        timeout=5.0,
        required_components=["database", "redis", "celery", "kafka"],
    )

    # Strip component details if not requested
    if not detailed:
        system_health.components = {}

    return system_health


@router.get(
    "/health/detailed",
    summary="Detailed health status",
    response_model=SystemHealth,
)
async def detailed_health_check() -> SystemHealth:
    """
    Comprehensive health check with full component details.

    Checks all service components and returns detailed status information
    including metadata, error messages, and uptime.

    Use this for troubleshooting, monitoring dashboards, or detailed status pages.

    Returns:
        SystemHealth: Complete health status with all component details
    """
    checker = get_health_checker()
    return await checker.check_all(timeout=5.0)

