"""Ingestion API endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ...adapters import get_adapter
from ...exceptions import AdapterNotFoundError, ScryIngestorError
from ...messaging.publisher import get_ingestion_publisher
from ...models.repository import build_error_record, build_success_record, persist_ingestion_record
from ...monitoring.metrics import record_ingestion_attempt, record_ingestion_error
from ...schemas.payload import IngestionRequest, IngestionResponse
from ...utils.logging import log_ingestion_attempt, setup_logger
from ..dependencies import require_api_key

logger = setup_logger(__name__, context={"adapter_type": "IngestionAPI"})
router = APIRouter(dependencies=[Depends(require_api_key)])


def _persist_success(
    payload: IngestionResponse,
    validation_summary: dict[str, Any],
) -> None:
    """Persist successful ingestion metadata for observability."""

    if payload.payload is None:
        return

    persist_ingestion_record(build_success_record(payload.payload, validation_summary))


def _persist_error(
    *,
    adapter_type: str,
    source_id: str,
    correlation_id: str | None,
    validation_summary: dict[str, Any],
    error_details: dict[str, Any],
    duration_ms: int | None = None,
) -> None:
    """Persist failed ingestion metadata for diagnostics."""

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


@router.post("/ingest", response_model=IngestionResponse)
async def ingest_data(request: IngestionRequest) -> IngestionResponse:
    """
    Ingest data from a source using the specified adapter.

    Args:
        request: Ingestion request with adapter type and configuration

    Returns:
        IngestionResponse with payload or error details
    """
    try:
        # Get the adapter class
        adapter_class = get_adapter(request.adapter_type)

        # Create adapter instance with config
        adapter = adapter_class(request.source_config)

        # Process the data
        payload = await adapter.process()

        # Add correlation ID if provided
        if request.correlation_id:
            payload.metadata.correlation_id = request.correlation_id

        # Log successful ingestion
        record_ingestion_attempt(
            adapter=payload.metadata.adapter_type,
            status="success",
        )

        validation_summary = {
            "is_valid": payload.validation.is_valid,
            "error_count": len(payload.validation.errors),
            "warning_count": len(payload.validation.warnings),
            "metrics": payload.validation.metrics,
        }

        log_ingestion_attempt(
            logger=logger,
            source_id=payload.metadata.source_id,
            adapter_type=payload.metadata.adapter_type,
            duration_ms=payload.metadata.processing_duration_ms,
            status="success",
            correlation_id=request.correlation_id,
            validation_summary=validation_summary,
        )

        get_ingestion_publisher().publish_success(payload)

        response = IngestionResponse(
            status="success",
            message=f"Data ingested successfully from {request.adapter_type}",
            payload=payload,
            error_details=None
        )

        _persist_success(response, validation_summary)
        return response

    except AdapterNotFoundError as e:
        source_id = request.source_config.get("source_id", "unknown")
        record_ingestion_attempt(adapter=request.adapter_type, status="error")
        record_ingestion_error(error_type=e.__class__.__name__)
        error_details = {"error_type": e.__class__.__name__, "message": str(e)}
        error_validation_summary = {
            "is_valid": False,
            "error_count": 1,
            "warning_count": 0,
            "metrics": {},
            "errors": [str(e)],
        }
        log_ingestion_attempt(
            logger=logger,
            source_id=source_id,
            adapter_type=request.adapter_type,
            duration_ms=0,
            status="error",
            correlation_id=request.correlation_id,
            validation_summary=error_validation_summary,
            error=str(e),
        )
        logger.error(
            "Adapter not found: %s",
            e,
            extra={
                "source_id": source_id,
                "adapter_type": request.adapter_type,
                "correlation_id": request.correlation_id or "-",
                "status": "error",
                "duration_ms": 0,
                "validation_summary": json.dumps(
                    error_validation_summary,
                    default=str,
                    sort_keys=True,
                ),
            },
        )
        _persist_error(
            adapter_type=request.adapter_type,
            source_id=source_id,
            correlation_id=request.correlation_id,
            validation_summary=error_validation_summary,
            error_details=error_details,
            duration_ms=None,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ScryIngestorError as e:
        # Log failed ingestion
        record_ingestion_attempt(adapter=request.adapter_type, status="error")
        record_ingestion_error(error_type=e.__class__.__name__)

        error_messages = [str(e)]
        error_validation_summary = {
            "is_valid": False,
            "error_count": len(error_messages),
            "warning_count": 0,
            "metrics": {},
            "errors": error_messages,
        }

        log_ingestion_attempt(
            logger=logger,
            source_id=request.source_config.get("source_id", "unknown"),
            adapter_type=request.adapter_type,
            duration_ms=0,
            status="error",
            error=str(e),
            correlation_id=request.correlation_id,
            validation_summary=error_validation_summary,
        )

        response = IngestionResponse(
            payload=None,
            status="error",
            message=f"Ingestion failed: {str(e)}",
            error_details={"error_type": e.__class__.__name__, "message": str(e)},
        )
        _persist_error(
            adapter_type=request.adapter_type,
            source_id=request.source_config.get("source_id", "unknown"),
            correlation_id=request.correlation_id,
            validation_summary=error_validation_summary,
            error_details=response.error_details or {},
            duration_ms=0,
        )
        return response


@router.get("/ingest/adapters")
async def list_available_adapters() -> dict[str, list[str]]:
    """
    List all available data source adapters.

    Returns:
        Dictionary with list of adapter names
    """
    from ...adapters import list_adapters

    return {"adapters": list_adapters()}
