"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Expose Prometheus metrics collected by the service."""

    metrics_payload = generate_latest()
    return Response(content=metrics_payload, media_type=CONTENT_TYPE_LATEST)
