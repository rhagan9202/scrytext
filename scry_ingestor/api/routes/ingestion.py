"""Ingestion API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from ...adapters import get_adapter
from ...exceptions import AdapterNotFoundError, ScryIngestorError
from ...messaging.publisher import get_ingestion_publisher
from ...monitoring.metrics import record_ingestion_attempt, record_ingestion_error
from ...schemas.payload import IngestionRequest, IngestionResponse
from ...utils.logging import log_ingestion_attempt, setup_logger
from ..dependencies import require_api_key

logger = setup_logger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])


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

        log_ingestion_attempt(
            logger=logger,
            source_id=payload.metadata.source_id,
            adapter_type=payload.metadata.adapter_type,
            duration_ms=payload.metadata.processing_duration_ms,
            status="success",
            correlation_id=request.correlation_id,
        )

        get_ingestion_publisher().publish_success(payload)

        return IngestionResponse(
            status="success",
            message=f"Data ingested successfully from {request.adapter_type}",
            payload=payload,
            error_details=None
        )

    except AdapterNotFoundError as e:
        logger.error(f"Adapter not found: {e}")
        record_ingestion_attempt(adapter=request.adapter_type, status="error")
        record_ingestion_error(error_type=e.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ScryIngestorError as e:
        # Log failed ingestion
        record_ingestion_attempt(adapter=request.adapter_type, status="error")
        record_ingestion_error(error_type=e.__class__.__name__)

        log_ingestion_attempt(
            logger=logger,
            source_id=request.source_config.get("source_id", "unknown"),
            adapter_type=request.adapter_type,
            duration_ms=0,
            status="error",
            error=str(e),
            correlation_id=request.correlation_id,
        )

        return IngestionResponse(
            payload=None,
            status="error",
            message=f"Ingestion failed: {str(e)}",
            error_details={"error_type": e.__class__.__name__, "message": str(e)},
        )


@router.get("/ingest/adapters")
async def list_available_adapters() -> dict[str, list[str]]:
    """
    List all available data source adapters.

    Returns:
        Dictionary with list of adapter names
    """
    from ...adapters import list_adapters

    return {"adapters": list_adapters()}
