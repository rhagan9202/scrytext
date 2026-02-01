"""Ingestion API endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ...adapters import get_adapter
from ...exceptions import (
    AdapterNotFoundError,
    CollectionError,
    ConfigurationError,
    ScryIngestorError,
    TransformationError,
    ValidationError,
)
from ...messaging.publisher import get_ingestion_publisher
from ...models.repository import build_error_record, build_success_record, persist_ingestion_record
from ...monitoring.metrics import record_ingestion_attempt, record_ingestion_error
from ...schemas.payload import AdapterListResponse, IngestionRequest, IngestionResponse
from ...utils.logging import log_ingestion_attempt, setup_logger
from ..dependencies import require_api_key

logger = setup_logger(__name__, context={"adapter_type": "IngestionAPI"})
router = APIRouter(dependencies=[Depends(require_api_key)])


def _status_code_for_error(exc: ScryIngestorError) -> int:
    """Map ingestion errors to appropriate HTTP status codes."""

    if isinstance(exc, ValidationError):
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    if isinstance(exc, (ConfigurationError, CollectionError)):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, TransformationError):
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    return status.HTTP_500_INTERNAL_SERVER_ERROR


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


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    summary="Execute data ingestion with a registered adapter",
    description=(
        "Run the ingestion pipeline using one of the registered adapters. "
        "The request payload determines which adapter is used and how the source "
        "data is fetched."
    ),
    response_description="Standardized ingestion payload with validation metadata.",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid adapter configuration or source input.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing or invalid API key.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "API key authenticated but not authorized.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Requested adapter is not registered.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Adapter validation failed for the provided input.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unhandled ingestion failure.",
        },
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "adapter_type": "pdf",
                        "source_config": {
                            "source_id": "invoice-2024-09-15",
                            "path": "s3://enterprise-data/documents/invoice.pdf",
                            "use_cloud_processing": True,
                            "transformation": {
                                "extract_metadata": True,
                                "extract_tables": False,
                                "combine_pages": True,
                            },
                        },
                        "correlation_id": "3d0dfb58-3f23-4a7a-9b60-5d0a4ffbc9dd",
                    }
                }
            }
        }
    },
)
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
        adapter_config = dict(request.source_config)
        adapter_config.setdefault("adapter_type", request.adapter_type)
        adapter = adapter_class(adapter_config)

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
        return JSONResponse(
            status_code=_status_code_for_error(e),
            content=response.model_dump(mode="json"),
        )


@router.get(
    "/ingest/adapters",
    response_model=AdapterListResponse,
    summary="List registered data source adapters",
    description=(
        "Retrieve the identifiers of all adapters currently registered with the "
        "ingestion service."
    ),
    response_description="Adapter identifiers available for use in ingestion requests.",
)
async def list_available_adapters() -> AdapterListResponse:
    """
    List all available data source adapters.

    Returns:
        Dictionary with list of adapter names
    """
    from ...adapters import list_adapters

    return AdapterListResponse(adapters=list_adapters())
