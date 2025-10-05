"""Celery task package exposing the configured app and ingestion tasks."""

from __future__ import annotations

from .celery_app import celery_app as app
from .ingestion import INGESTION_TASKS, run_ingestion_pipeline

__all__ = [
    "app",
    "INGESTION_TASKS",
    "run_ingestion_pipeline",
]
