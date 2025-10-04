"""Pydantic schemas for ingestion payloads and validation results."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValidationResult(BaseModel):
    """Data quality metrics and validation errors."""

    is_valid: bool = Field(..., description="Overall validation status")
    errors: list[str] = Field(default_factory=list, description="Validation error messages")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Quality metrics (e.g., completeness, record count)"
    )


class IngestionMetadata(BaseModel):
    """Metadata about the ingestion process."""

    source_id: str = Field(..., description="Unique identifier for data source")
    adapter_type: str = Field(..., description="Type of adapter used")
    timestamp: str = Field(..., description="ISO format timestamp of ingestion")
    processing_duration_ms: int = Field(..., description="Processing time in milliseconds")
    processing_mode: str = Field(..., description="Processing mode: 'local' or 'cloud'")
    correlation_id: str | None = Field(None, description="Correlation ID for tracing")


class IngestionPayload(BaseModel):
    """Standardized payload structure for all ingested data."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Any = Field(..., description="Processed data (text, JSON, or DataFrame)")
    metadata: IngestionMetadata = Field(..., description="Ingestion metadata")
    validation: ValidationResult = Field(..., description="Validation results")


class IngestionRequest(BaseModel):
    """Request schema for ingestion API endpoints."""

    adapter_type: str = Field(..., description="Type of adapter to use")
    source_config: dict[str, Any] = Field(..., description="Adapter-specific configuration")
    correlation_id: str | None = Field(None, description="Optional correlation ID for tracing")


class IngestionResponse(BaseModel):
    """Response schema for ingestion API endpoints."""

    status: str = Field(..., description="Status: 'success' or 'error'")
    message: str = Field(..., description="Human-readable status message")
    payload: IngestionPayload | None = Field(None, description="Ingestion payload if successful")
    error_details: dict[str, Any] | None = Field(None, description="Error details if failed")
