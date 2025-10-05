"""Celery application configuration for Scry_Ingestor."""

from __future__ import annotations

from celery import Celery

from ..utils.config import get_settings


def _resolve_redis_url() -> str:
    """Return the Redis URL configured for the application."""

    settings = get_settings()
    return settings.redis_url or "redis://localhost:6379/0"


celery_app = Celery(
    "scry_ingestor",
    broker=_resolve_redis_url(),
    backend=_resolve_redis_url(),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
)

celery_app.autodiscover_tasks(["scry_ingestor.tasks"])