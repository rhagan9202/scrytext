"""Ingestion API endpoints."""

from fastapi import APIRouter, HTTPException, status

from ...adapters import get_adapter
from ...exceptions import AdapterNotFoundError, ScryIngestorError
from ...schemas.payload import IngestionRequest, IngestionResponse
from ...utils.logging import log_ingestion_attempt, setup_logger

logger = setup_logger(__name__)
router = APIRouter()


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
        log_ingestion_attempt(
            logger=logger,
            source_id=payload.metadata.source_id,
            adapter_type=payload.metadata.adapter_type,
            duration_ms=payload.metadata.processing_duration_ms,
            status="success",
            correlation_id=request.correlation_id,
        )

        return IngestionResponse(
            status="success",
            message=f"Data ingested successfully from {request.adapter_type}",
            payload=payload,
            error_details=None
        )

    except AdapterNotFoundError as e:
        logger.error(f"Adapter not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ScryIngestorError as e:
        # Log failed ingestion
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
