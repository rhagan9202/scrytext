"""Health check endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...messaging.publisher import get_ingestion_publisher

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint including Kafka connectivity status."""

    kafka_status = get_ingestion_publisher().health_status()

    overall_status = "healthy"
    if kafka_status["status"] == "error":
        overall_status = "unhealthy"
    elif kafka_status["status"] == "degraded":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "service": "scry_ingestor",
        "kafka": kafka_status,
    }
