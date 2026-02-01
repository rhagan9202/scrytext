"""Celery ingestion tasks for adapter pipelines."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar, cast

from celery import Task

from ..adapters import get_adapter, list_adapters
from ..exceptions import (
    AdapterNotFoundError,
    CircuitBreakerOpenError,
    CollectionError,
    ConfigurationError,
    ScryIngestorError,
    TaskExecutionError,
    TransformationError,
    ValidationError,
)
from ..messaging.publisher import get_ingestion_publisher
from ..models.repository import build_error_record, build_success_record, persist_ingestion_record
from ..monitoring.metrics import record_ingestion_attempt, record_ingestion_error
from ..schemas.payload import IngestionPayload
from ..utils.config import GlobalSettings, ensure_runtime_configuration, get_settings
from ..utils.logging import log_ingestion_attempt, setup_logger
from .celery_app import celery_app
from .circuit_breaker import get_circuit_breaker
from .error_handling import build_error_report, build_failure_summary
from .policies import CeleryRetryPolicy

logger = setup_logger(__name__, context={"adapter_type": "CeleryTasks"})

INGESTION_TASKS: dict[str, Task] = {}

RETRYABLE_ERROR_REGISTRY: dict[str, type[Exception]] = {
    "CollectionError": CollectionError,
    "TransformationError": TransformationError,
    "ValidationError": ValidationError,
}

T = TypeVar("T")


def _run_coroutine(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine from sync context, even when an event loop is active."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    result_container: dict[str, T] = {}
    error_container: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result_container["result"] = asyncio.run(coro_factory())
        except BaseException as exc:
            error_container["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if error_container:
        raise error_container["error"]
    return result_container["result"]


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

    normalized_config.setdefault("adapter_type", adapter_name)
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


def _resolve_retry_policy(config: dict[str, Any], settings: GlobalSettings) -> CeleryRetryPolicy:
    """Derive the Celery retry policy from adapter configuration and defaults."""

    raw_policy = config.get("celery_retry")
    if raw_policy is None:
        return CeleryRetryPolicy.with_overrides(
            enabled=False,
            max_attempts=settings.celery_max_retries,
            backoff_seconds=settings.celery_retry_backoff_seconds,
            max_backoff_seconds=settings.celery_retry_max_backoff_seconds,
        )

    if not isinstance(raw_policy, Mapping):
        raise ConfigurationError("celery_retry must be a mapping when provided")

    enabled = bool(raw_policy.get("enabled", False))

    try:
        max_attempts = int(raw_policy.get("max_attempts", settings.celery_max_retries))
    except (TypeError, ValueError) as exc:  # pragma: no cover - configuration guarding
        raise ConfigurationError("celery_retry.max_attempts must be an integer") from exc
    if max_attempts < 0:
        raise ConfigurationError("celery_retry.max_attempts must be >= 0")

    try:
        backoff_seconds = float(
            raw_policy.get("backoff_seconds", settings.celery_retry_backoff_seconds)
        )
        max_backoff_seconds = float(
            raw_policy.get("max_backoff_seconds", settings.celery_retry_max_backoff_seconds)
        )
    except (TypeError, ValueError) as exc:  # pragma: no cover - configuration guarding
        raise ConfigurationError("celery_retry backoff values must be numeric") from exc

    if backoff_seconds <= 0:
        raise ConfigurationError("celery_retry.backoff_seconds must be greater than zero")
    if max_backoff_seconds <= 0:
        raise ConfigurationError("celery_retry.max_backoff_seconds must be greater than zero")
    if max_backoff_seconds < backoff_seconds:
        raise ConfigurationError(
            "celery_retry.max_backoff_seconds must be >= celery_retry.backoff_seconds"
        )

    retryable_errors_raw = raw_policy.get("retryable_errors")
    retryable_exceptions: list[type[Exception]] | None = None
    if retryable_errors_raw is not None:
        if not isinstance(retryable_errors_raw, list | tuple | set):
            raise ConfigurationError(
                "celery_retry.retryable_errors must be a sequence of exception names"
            )
        retryable_exceptions = []
        for entry in retryable_errors_raw:
            if not isinstance(entry, str):
                raise ConfigurationError(
                    "celery_retry.retryable_errors entries must be string names"
                )
            normalized = entry.strip()
            if normalized not in RETRYABLE_ERROR_REGISTRY:
                valid = ", ".join(sorted(RETRYABLE_ERROR_REGISTRY))
                raise ConfigurationError(
                    f"Unsupported retryable error '{normalized}'. Valid options: {valid}"
                )
            retryable_exceptions.append(RETRYABLE_ERROR_REGISTRY[normalized])
        if not retryable_exceptions:
            raise ConfigurationError(
                "celery_retry.retryable_errors must contain at least one error type when provided"
            )

    return CeleryRetryPolicy.with_overrides(
        enabled=enabled,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        retryable_exceptions=retryable_exceptions,
    )


def _handle_task_error(
    exc: Exception,
    *,
    adapter_name: str,
    source_id: str,
    correlation_id: str | None,
    policy: CeleryRetryPolicy,
    status: str,
    duration_ms: int | None = None,
    retryable_override: bool | None = None,
    extra_details: dict[str, Any] | None = None,
) -> TaskExecutionError:
    """Build structured error artifacts, persist them, and return `TaskExecutionError`."""

    details = {"retry_policy": policy.to_dict()}
    if extra_details:
        details.update(extra_details)

    report = build_error_report(
        exc,
        adapter_type=adapter_name,
        source_id=source_id,
        correlation_id=correlation_id,
        retryable_override=retryable_override,
        extra_details=details,
    )
    summary = build_failure_summary(report)

    record_ingestion_attempt(adapter=adapter_name, status=status)
    record_ingestion_error(report.error_type)
    log_ingestion_attempt(
        logger=logger,
        source_id=source_id,
        adapter_type=adapter_name,
        duration_ms=duration_ms or 0,
        status=status,
        correlation_id=correlation_id,
        validation_summary=summary,
        error=report.message,
        error_report=report.to_dict(),
    )

    _persist_error(
        adapter_type=adapter_name,
        source_id=source_id,
        correlation_id=correlation_id,
        validation_summary=summary,
        error_details=report.to_dict(),
        duration_ms=duration_ms,
    )

    return TaskExecutionError(report, original_error=exc, retry_policy=policy)


def run_ingestion_pipeline(adapter_name: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Execute the ingestion workflow synchronously for Celery workers."""

    settings = get_settings()
    ensure_runtime_configuration(settings)
    config, correlation_id = _prepare_source_config(adapter_name, request_payload)
    policy = _resolve_retry_policy(config, settings)
    source_id = config.get("source_id", "unknown")

    circuit = get_circuit_breaker()
    try:
        circuit.ensure_available(adapter_name)
    except CircuitBreakerOpenError as exc:
        error = _handle_task_error(
            exc,
            adapter_name=adapter_name,
            source_id=source_id,
            correlation_id=correlation_id,
            policy=policy,
            status="blocked",
            retryable_override=False,
            extra_details={
                "circuit_open_until": exc.reopen_at.isoformat() if exc.reopen_at else None,
            },
        )
        raise error from exc

    try:
        adapter_cls = get_adapter(adapter_name)
        adapter = adapter_cls(config)
        payload = _run_coroutine(adapter.process)
    except AdapterNotFoundError as exc:
        circuit.record_failure(adapter_name)
        error = _handle_task_error(
            exc,
            adapter_name=adapter_name,
            source_id=source_id,
            correlation_id=correlation_id,
            policy=policy,
            status="error",
            retryable_override=False,
            extra_details={"available_adapters": sorted(list_adapters())},
        )
        raise error from exc
    except ScryIngestorError as exc:
        circuit.record_failure(adapter_name)
        error = _handle_task_error(
            exc,
            adapter_name=adapter_name,
            source_id=source_id,
            correlation_id=correlation_id,
            policy=policy,
            status="error",
            retryable_override=policy.should_retry(exc),
        )
        raise error from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        circuit.record_failure(adapter_name)
        error = _handle_task_error(
            exc,
            adapter_name=adapter_name,
            source_id=source_id,
            correlation_id=correlation_id,
            policy=policy,
            status="error",
            retryable_override=policy.should_retry(exc),
        )
        raise error from exc

    circuit.record_success(adapter_name)

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
        retry_policy=policy.to_dict(),
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

    settings = get_settings()

    @celery_app.task(name=task_name, bind=True, max_retries=settings.celery_max_retries)
    def _task(
        self: Any,
        request_payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run the ingestion pipeline for the bound adapter."""

        if request_payload is None:
            request_payload = {}
        if kwargs:
            merged_payload = dict(request_payload)
            merged_payload.update(kwargs)
            request_payload = merged_payload

        try:
            return run_ingestion_pipeline(adapter_name, request_payload)
        except TaskExecutionError as exc:
            policy = exc.retry_policy or CeleryRetryPolicy.with_overrides(
                enabled=False,
                max_attempts=settings.celery_max_retries,
                backoff_seconds=settings.celery_retry_backoff_seconds,
                max_backoff_seconds=settings.celery_retry_max_backoff_seconds,
            )

            current_retries = getattr(self.request, "retries", 0)
            if exc.report.retryable and policy.enabled and current_retries < policy.max_attempts:
                countdown = policy.next_countdown(current_retries)
                logger.warning(
                    "Retrying Celery ingestion task after failure",
                    extra={
                        "adapter_type": adapter_name,
                        "status": "retry",
                        "retry_count": current_retries + 1,
                        "countdown": countdown,
                        "retryable": True,
                    },
                )
                raise self.retry(
                    exc=exc,
                    countdown=countdown,
                    max_retries=policy.max_attempts,
                )

            raise

    INGESTION_TASKS[adapter_name] = cast(Task, _task)


for adapter_key in list_adapters():
    _register_task(adapter_key)


__all__ = [
    "INGESTION_TASKS",
    "run_ingestion_pipeline",
]
