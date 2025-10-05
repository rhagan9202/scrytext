"""Logging configuration for Scry_Ingestor."""

from __future__ import annotations

import json
import logging
import sys
from threading import Lock
from typing import Any, Final

from .config import get_settings

# Define log format with structured context placeholders.
LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "source_id=%(source_id)s | adapter=%(adapter_type)s | "
    "correlation_id=%(correlation_id)s | status=%(status)s | "
    "duration_ms=%(duration_ms)s | validation=%(validation_summary)s | %(message)s"
)

DEFAULT_CONTEXT: Final[dict[str, str]] = {
    "source_id": "-",
    "adapter_type": "-",
    "correlation_id": "-",
    "status": "-",
    "duration_ms": "-",
    "validation_summary": "-",
}

_LOG_CONFIGURED = False
_CONFIG_LOCK: Final = Lock()


class ContextualFormatter(logging.Formatter):
    """Formatter that injects default structured context fields when absent."""

    def __init__(self, fmt: str, defaults: dict[str, str] | None = None) -> None:
        super().__init__(fmt)
        self._defaults = defaults or {}

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        for key, value in self._defaults.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return super().format(record)


def _configure_root_logger() -> None:
    """Configure the root logger exactly once based on global settings."""

    global _LOG_CONFIGURED
    with _CONFIG_LOCK:
        if _LOG_CONFIGURED:
            return

        settings = get_settings()
        resolved_level = getattr(logging, settings.log_level.upper(), logging.INFO)

        root_logger = logging.getLogger()
        root_logger.setLevel(resolved_level)

        formatter = ContextualFormatter(LOG_FORMAT, DEFAULT_CONTEXT)

        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(resolved_level)
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)
        else:
            for handler in root_logger.handlers:
                handler.setLevel(resolved_level)
                handler.setFormatter(formatter)

        _LOG_CONFIGURED = True


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that lets per-call extras override defaults."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        base_extra = self.extra or {}
        extra = dict(base_extra)
        provided_extra = kwargs.get("extra") or {}
        extra.update(provided_extra)
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logger(
    name: str,
    *,
    level: str | None = None,
    context: dict[str, Any] | None = None,
) -> logging.LoggerAdapter:
    """Return a logger configured with the global logging defaults.

    Args:
        name: Logger name to retrieve.
        level: Optional log level override (primarily for tests).
        context: Optional default structured context to include with every entry.

    Returns:
        LoggerAdapter injecting structured defaults for consistent formatting.
    """

    _configure_root_logger()
    logger = logging.getLogger(name)

    if level is not None:
        resolved_value = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(resolved_value)
    else:
        logger.setLevel(logging.NOTSET)

    adapter_context: dict[str, Any] = dict(DEFAULT_CONTEXT)
    if context:
        for key, value in context.items():
            adapter_context[key] = value

    return StructuredLoggerAdapter(logger, adapter_context)


def log_ingestion_attempt(
    logger: logging.Logger | logging.LoggerAdapter,
    source_id: str,
    adapter_type: str,
    duration_ms: int,
    status: str,
    **extra_context: Any,
) -> None:
    """
    Log an ingestion attempt with structured context.

    Args:
        logger: Logger instance
        source_id: Source identifier
        adapter_type: Type of adapter used
        duration_ms: Processing duration in milliseconds
        status: Status (success, error, etc.)
        **extra_context: Additional context to log
    """
    correlation_id = extra_context.pop("correlation_id", None)
    validation_summary_raw = extra_context.pop("validation_summary", None)

    summary_value = "-"
    if validation_summary_raw is not None:
        summary_value = json.dumps(validation_summary_raw, default=str, sort_keys=True)

    structured_context: dict[str, Any] = {
        "source_id": source_id,
        "adapter_type": adapter_type,
        "duration_ms": duration_ms,
        "status": status,
        "correlation_id": correlation_id or extra_context.get("correlation_id", "-"),
        "validation_summary": summary_value,
    }
    additional_context = {
        key: value for key, value in extra_context.items() if key not in structured_context
    }
    structured_context.update(additional_context)
    message_parts = []
    if summary_value != "-":
        message_parts.append(f"validation={summary_value}")
    if additional_context:
        message_parts.append(f"context={additional_context}")
    message_suffix = f" | {' | '.join(message_parts)}" if message_parts else ""

    status_value = status or "unknown"
    log_method = logger.info if status_value.lower() == "success" else logger.error
    log_method(f"Ingestion {status_value}{message_suffix}", extra=structured_context)
