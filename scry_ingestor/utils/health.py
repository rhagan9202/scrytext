"""Health checking utilities for operational readiness."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    name: str = Field(..., description="Component name")
    status: HealthStatus = Field(..., description="Health status")
    message: str | None = Field(None, description="Status message or error details")
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of health check",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional component metadata"
    )


class SystemHealth(BaseModel):
    """Overall system health status."""

    status: HealthStatus = Field(..., description="Overall system health")
    service: str = Field("scry_ingestor", description="Service name")
    version: str = Field("1.0.0", description="Service version")
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of health check",
    )
    components: dict[str, ComponentHealth] = Field(
        default_factory=dict, description="Component health statuses"
    )
    uptime_seconds: float | None = Field(None, description="Service uptime in seconds")


class HealthChecker:
    """Centralized health checking for all service dependencies."""

    def __init__(self) -> None:
        """Initialize health checker with registered components."""
        self._checks: dict[str, Callable[[], Any]] = {}
        self._start_time = datetime.now(timezone.utc)
        self._executor = ThreadPoolExecutor(thread_name_prefix="scry-ingestor-health")

    async def _run_sync_check(self, check_fn: Callable[[], Any]) -> Any:
        future = self._executor.submit(check_fn)
        try:
            while not future.done():
                await asyncio.sleep(0.01)
            return future.result()
        except asyncio.CancelledError:
            future.cancel()
            raise

    def register_check(self, component_name: str, check_fn: Callable[[], Any]) -> None:
        """
        Register a health check for a component.

        Args:
            component_name: Name of the component to check
            check_fn: Async or sync function that returns ComponentHealth
        """
        self._checks[component_name] = check_fn

    async def check_component(self, component_name: str) -> ComponentHealth:
        """
        Check health of a specific component.

        Args:
            component_name: Name of component to check

        Returns:
            ComponentHealth status for the component

        Raises:
            KeyError: If component is not registered
        """
        if component_name not in self._checks:
            return ComponentHealth(
                name=component_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Component '{component_name}' not registered",
            )

        check_fn = self._checks[component_name]
        try:
            if asyncio.iscoroutinefunction(check_fn):
                result = await check_fn()
            else:
                result = await self._run_sync_check(check_fn)
            return result
        except Exception as e:
            return ComponentHealth(
                name=component_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
            )

    async def check_all(
        self, timeout: float = 5.0, required_components: list[str] | None = None
    ) -> SystemHealth:
        """
        Check health of all registered components.

        Args:
            timeout: Maximum time to wait for all checks (seconds)
            required_components: List of component names that must be healthy for
                                 system to be considered healthy. If None, all
                                 components are required.

        Returns:
            SystemHealth with overall status and component details
        """
        components: dict[str, ComponentHealth] = {}
        required = set(required_components or self._checks.keys())

        try:
            # Run all checks concurrently with timeout
            check_tasks = {
                name: asyncio.create_task(self.check_component(name))
                for name in self._checks.keys()
            }

            done, pending = await asyncio.wait(
                check_tasks.values(), timeout=timeout, return_when=asyncio.ALL_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # Collect results
            for name, task in check_tasks.items():
                if task in done:
                    try:
                        components[name] = task.result()
                    except Exception as e:
                        components[name] = ComponentHealth(
                            name=name,
                            status=HealthStatus.UNHEALTHY,
                            message=f"Check exception: {e}",
                        )
                else:
                    components[name] = ComponentHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message="Health check timed out",
                    )

        except Exception:
            # Catastrophic failure in health checking system
            return SystemHealth(
                status=HealthStatus.UNHEALTHY,
                service="scry_ingestor",
                version="1.0.0",
                components={},
                uptime_seconds=self._get_uptime_seconds(),
                checked_at=datetime.now(timezone.utc),
            )

        # Determine overall status
        overall_status = self._calculate_overall_status(components, required)

        return SystemHealth(
            status=overall_status,
            service="scry_ingestor",
            version="1.0.0",
            components=components,
            uptime_seconds=self._get_uptime_seconds(),
            checked_at=datetime.now(timezone.utc),
        )

    def _calculate_overall_status(
        self, components: dict[str, ComponentHealth], required: set[str]
    ) -> HealthStatus:
        """Calculate overall system status from component statuses."""
        if not components:
            return HealthStatus.UNHEALTHY

        # Check required components
        required_statuses = [
            comp.status for name, comp in components.items() if name in required
        ]

        if not required_statuses:
            return HealthStatus.HEALTHY

        if any(status == HealthStatus.UNHEALTHY for status in required_statuses):
            return HealthStatus.UNHEALTHY

        if any(status == HealthStatus.DEGRADED for status in required_statuses):
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def _get_uptime_seconds(self) -> float:
        """Get service uptime in seconds."""
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()


# Global health checker instance
_health_checker: HealthChecker | None = None


def get_health_checker() -> HealthChecker:
    """Get or create global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
