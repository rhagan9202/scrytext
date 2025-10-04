"""Logging configuration for Scry_Ingestor."""

import logging
import sys
from typing import Any

# Define log format with structured context
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name (typically __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger


def log_ingestion_attempt(
    logger: logging.Logger,
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
    log_data = {
        "source_id": source_id,
        "adapter_type": adapter_type,
        "duration_ms": duration_ms,
        "status": status,
        **extra_context,
    }

    if status == "success":
        logger.info(f"Ingestion completed: {log_data}")
    else:
        logger.error(f"Ingestion failed: {log_data}")
