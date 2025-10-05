"""Celery ingestion tasks for adapter pipelines."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from celery import Task

from ..adapters import get_adapter, list_adapters
from ..exceptions import AdapterNotFoundError, ScryIngestorError
from ..messaging.publisher import get_ingestion_publisher
from ..models.repository import build_error_record, build_success_record, persist_ingestion_record
from ..monitoring.metrics import record_ingestion_attempt, record_ingestion_error
from ..schemas.payload import IngestionPayload
from ..utils.config import ensure_runtime_configuration, get_settings
from ..utils.logging import log_ingestion_attempt, setup_logger
from .celery_app import celery_app

logger = setup_logger(__name__, context={"adapter_type": "CeleryTasks"})

INGESTION_TASKS: dict[str, Task] = {}


def _persist_success(payload: IngestionPayload, validation_summary: dict[str, Any]) -> None:
    """Persist a successful ingestion result executed by a Celery worker."""

    persist_ingestion_record(build_success_record(payload, validation_summary))


def _persist_error(
    *,
    adapter_type: str,
    source_id: str,
    correlation_id: str | None,
    validation_summary: dict[str, Any],
    error_details: dict[str, Any],
    duration_ms: int | None = None,
) -> None:
    """Persist a failed ingestion attempt executed by a Celery worker."""

    persist_ingestion_record(
        build_error_record(
            adapter_type=adapter_type,
            source_id=source_id,
            correlation_id=correlation_id,
            validation_summary=validation_summary,
            error_details=error_details,
            duration_ms=duration_ms,
        )
    )


def _prepare_source_config(
    adapter_name: str,
    request_payload: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Extract and normalize the source configuration from the request."""

    source_config = request_payload.get("source_config")
    if not isinstance(source_config, dict):
        raise ValueError(
            "`source_config` must be provided as a dictionary for adapter ingestion tasks."
        )

    correlation_id = request_payload.get("correlation_id")
    normalized_config = dict(source_config)
    if correlation_id and "correlation_id" not in normalized_config:
        normalized_config["correlation_id"] = correlation_id

    normalized_config.setdefault("source_id", f"{adapter_name}-source")

    return normalized_config, correlation_id


def _validation_summary(payload: IngestionPayload) -> dict[str, Any]:
    """Build a validation summary dictionary for logging and events."""

    validation = payload.validation
    return {
        "is_valid": validation.is_valid,
        "error_count": len(validation.errors),
        "warning_count": len(validation.warnings),
        "metrics": validation.metrics,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }


def run_ingestion_pipeline(adapter_name: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Execute the ingestion workflow synchronously for Celery workers."""

    ensure_runtime_configuration(get_settings())
    config, correlation_id = _prepare_source_config(adapter_name, request_payload)

    try:
        adapter_cls = get_adapter(adapter_name)
        adapter = adapter_cls(config)
        payload = asyncio.run(adapter.process())
    except AdapterNotFoundError:
        record_ingestion_attempt(adapter=adapter_name, status="error")
        record_ingestion_error("AdapterNotFoundError")
        logger.exception(
            "Adapter not found for Celery ingestion task",
            extra={
                "adapter_type": adapter_name,
                "source_id": config.get("source_id", "unknown"),
                "correlation_id": correlation_id or "-",
                "status": "error",
            },
        )
        error_details = {
            "error_type": "AdapterNotFoundError",
            "message": f"Adapter '{adapter_name}' not registered",
        }
        error_summary = {
            "is_valid": False,
            "error_count": 1,
            "warning_count": 0,
            "metrics": {},
            "errors": [error_details["message"]],
        }
        _persist_error(
            adapter_type=adapter_name,
            source_id=config.get("source_id", "unknown"),
            correlation_id=correlation_id,
            validation_summary=error_summary,
            error_details=error_details,
        )
        raise
    except ScryIngestorError as exc:
        record_ingestion_attempt(adapter=adapter_name, status="error")
        record_ingestion_error(exc.__class__.__name__)
        error_details = {"error_type": exc.__class__.__name__, "message": str(exc)}
        error_summary = {
            "is_valid": False,
            "error_count": 1,
            "warning_count": 0,
            "metrics": {},
            "errors": [str(exc)],
        }
        log_ingestion_attempt(
            logger=logger,
            source_id=config.get("source_id", "unknown"),
            adapter_type=adapter_name,
            duration_ms=0,
            status="error",
            error=str(exc),
            correlation_id=correlation_id,
            validation_summary=error_summary,
        )
        _persist_error(
            adapter_type=adapter_name,
            source_id=config.get("source_id", "unknown"),
            correlation_id=correlation_id,
            validation_summary=error_summary,
            error_details=error_details,
            duration_ms=0,
        )
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        record_ingestion_attempt(adapter=adapter_name, status="error")
        record_ingestion_error(exc.__class__.__name__)
        logger.exception(
            "Unexpected error during ingestion task",
            extra={
                "adapter_type": adapter_name,
                "source_id": config.get("source_id", "unknown"),
                "correlation_id": correlation_id or "-",
                "status": "error",
            },
        )
        error_details = {"error_type": exc.__class__.__name__, "message": str(exc)}
        error_summary = {
            "is_valid": False,
            "error_count": 1,
            "warning_count": 0,
            "metrics": {},
            "errors": [str(exc)],
        }
        log_ingestion_attempt(
            logger=logger,
            source_id=config.get("source_id", "unknown"),
            adapter_type=adapter_name,
            duration_ms=0,
            status="error",
            error=str(exc),
            correlation_id=correlation_id,
            validation_summary=error_summary,
        )
        _persist_error(
            adapter_type=adapter_name,
            source_id=config.get("source_id", "unknown"),
            correlation_id=correlation_id,
            validation_summary=error_summary,
            error_details=error_details,
            duration_ms=0,
        )
        raise

    if correlation_id and payload.metadata.correlation_id is None:
        payload.metadata.correlation_id = correlation_id

    summary = _validation_summary(payload)

    record_ingestion_attempt(adapter=payload.metadata.adapter_type, status="success")
    log_ingestion_attempt(
        logger=logger,
        source_id=payload.metadata.source_id,
        adapter_type=payload.metadata.adapter_type,
        duration_ms=payload.metadata.processing_duration_ms,
        status="success",
        correlation_id=payload.metadata.correlation_id,
        validation_summary=summary,
    )

    _persist_success(payload, summary)
    get_ingestion_publisher().publish_success(payload)

    return {
        "status": "success",
        "message": f"Data ingested successfully from {adapter_name}",
        "payload": payload.model_dump(mode="json"),
        "error_details": None,
    }


def _register_task(adapter_name: str) -> None:
    """Register a Celery task for the provided adapter name."""

    task_name = f"ingest_{adapter_name}_task"

    @celery_app.task(name=task_name, bind=True)
    def _task(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        """Run the ingestion pipeline for the bound adapter."""

        return run_ingestion_pipeline(adapter_name, request_payload)

    INGESTION_TASKS[adapter_name] = cast(Task, _task)


for adapter_key in list_adapters():
    _register_task(adapter_key)


__all__ = [
    "INGESTION_TASKS",
    "run_ingestion_pipeline",
]
