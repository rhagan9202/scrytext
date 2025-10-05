"""Avro schemas and helpers for ingestion events."""

from __future__ import annotations

from typing import Any

from ..schemas.payload import IngestionPayload

INGESTION_EVENT_SCHEMA: dict[str, Any] = {
    "namespace": "scry.ingestion",
    "type": "record",
    "name": "IngestionEvent",
    "fields": [
        {"name": "correlation_id", "type": ["null", "string"], "default": None},
        {"name": "adapter", "type": "string"},
        {"name": "source_id", "type": "string"},
        {"name": "status", "type": "string"},
        {"name": "duration_ms", "type": "long"},
        {"name": "timestamp", "type": "string"},
        {
            "name": "validation",
            "type": {
                "type": "record",
                "name": "ValidationSummary",
                "fields": [
                    {"name": "is_valid", "type": "boolean"},
                    {"name": "error_count", "type": "int"},
                    {"name": "warning_count", "type": "int"},
                ],
            },
        },
        {"name": "metrics", "type": {"type": "map", "values": "string"}, "default": {}},
    ],
}


def build_ingestion_event_record(
    payload: IngestionPayload,
    status: str = "success",
) -> dict[str, Any]:
    """Transform an :class:`IngestionPayload` into an Avro-ready record."""

    validation = payload.validation
    metrics_map = {key: str(value) for key, value in validation.metrics.items()}

    return {
        "correlation_id": payload.metadata.correlation_id,
        "adapter": payload.metadata.adapter_type,
        "source_id": payload.metadata.source_id,
        "status": status,
        "duration_ms": payload.metadata.processing_duration_ms,
        "timestamp": payload.metadata.timestamp,
        "validation": {
            "is_valid": validation.is_valid,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings),
        },
        "metrics": metrics_map,
    }
