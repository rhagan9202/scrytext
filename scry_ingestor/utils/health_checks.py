"""Component health check implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from ..messaging.publisher import get_ingestion_publisher
from ..tasks.celery_app import celery_app
from ..utils.config import get_settings
from .health import ComponentHealth, HealthStatus

if TYPE_CHECKING:
    import redis


def check_database() -> ComponentHealth:
    """Check database connectivity."""
    try:
        # Use sync connection for health check
        from sqlalchemy import create_engine

        settings = get_settings()
        if not settings.database_url:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database URL not configured",
            )

        engine = create_engine(settings.database_url, pool_pre_ping=True)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

        engine.dispose()

        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database connection successful",
            metadata={"driver": "postgresql+psycopg2"},
        )
    except Exception as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database connection failed: {e}",
        )


def check_redis() -> ComponentHealth:
    """Check Redis connectivity."""
    try:
        import redis as redis_lib

        settings = get_settings()
        redis_url = settings.redis_url or "redis://localhost:6379/0"

        client: redis.Redis = redis_lib.from_url(redis_url, socket_timeout=2)  # type: ignore
        client.ping()
        server_info: dict = client.info("server")  # type: ignore

        client.close()

        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Redis connection successful",
            metadata={
                "version": server_info.get("redis_version"),
                "uptime_seconds": server_info.get("uptime_in_seconds"),
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message=f"Redis connection failed: {e}",
        )


def check_celery() -> ComponentHealth:
    """Check Celery worker connectivity."""
    try:
        # Inspect active workers
        inspect = celery_app.control.inspect(timeout=2.0)
        stats = inspect.stats()

        if not stats:
            return ComponentHealth(
                name="celery",
                status=HealthStatus.DEGRADED,
                message="No active Celery workers found",
            )

        worker_count = len(stats)
        return ComponentHealth(
            name="celery",
            status=HealthStatus.HEALTHY,
            message=f"{worker_count} worker(s) active",
            metadata={"workers": list(stats.keys()), "worker_count": worker_count},
        )
    except Exception as e:
        return ComponentHealth(
            name="celery",
            status=HealthStatus.UNHEALTHY,
            message=f"Celery inspection failed: {e}",
        )


def check_kafka() -> ComponentHealth:
    """Check Kafka/message queue connectivity."""
    try:
        publisher = get_ingestion_publisher()
        kafka_status = publisher.health_status()

        if kafka_status["status"] == "healthy":
            status = HealthStatus.HEALTHY
        elif kafka_status["status"] == "degraded":
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY

        return ComponentHealth(
            name="kafka",
            status=status,
            message=kafka_status.get("message", "Kafka status checked"),
            metadata=kafka_status,
        )
    except Exception as e:
        return ComponentHealth(
            name="kafka",
            status=HealthStatus.UNHEALTHY,
            message=f"Kafka check failed: {e}",
        )


def check_api() -> ComponentHealth:
    """Check API service health (always healthy if code is running)."""
    return ComponentHealth(
        name="api",
        status=HealthStatus.HEALTHY,
        message="API service is running",
    )


def register_all_health_checks() -> None:
    """Register all component health checks with the global health checker."""
    from .health import get_health_checker

    checker = get_health_checker()

    # Register health checks
    checker.register_check("database", check_database)
    checker.register_check("redis", check_redis)
    checker.register_check("celery", check_celery)
    checker.register_check("kafka", check_kafka)
    checker.register_check("api", check_api)
