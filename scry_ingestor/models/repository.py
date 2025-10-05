"""Repository helpers for persistence models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..schemas.payload import IngestionPayload
from .base import session_scope
from .ingestion_record import IngestionRecord


@dataclass(slots=True)
class IngestionRecordCreate:
    """Value object capturing required fields to persist an ingestion record."""

    source_id: str
    adapter_type: str
    status: str
    duration_ms: int | None = None
    correlation_id: str | None = None
    payload_metadata: dict[str, Any] | None = None
    validation_summary: dict[str, Any] | None = None
    error_details: dict[str, Any] | None = None


class IngestionRecordRepository:
    """Data access helpers for :class:`IngestionRecord`."""

    def __init__(self, session: Session):
        """Store the SQLAlchemy session used for persistence operations."""

        self._session = session

    def create(self, record_data: IngestionRecordCreate) -> IngestionRecord:
        """Persist a new ingestion record and return the mapped instance."""

        record = IngestionRecord(
            source_id=record_data.source_id,
            adapter_type=record_data.adapter_type,
            status=record_data.status,
            duration_ms=record_data.duration_ms,
            correlation_id=record_data.correlation_id,
            payload_metadata=record_data.payload_metadata,
            validation_summary=record_data.validation_summary,
            error_details=record_data.error_details,
        )
        self._session.add(record)
        self._session.flush()
        return record


def persist_ingestion_record(record_data: IngestionRecordCreate) -> IngestionRecord:
    """Create an ingestion record using a managed database session."""

    with session_scope() as session:
        repository = IngestionRecordRepository(session)
        record = repository.create(record_data)
        return record


def build_success_record(
    payload: IngestionPayload,
    validation_summary: dict[str, Any],
) -> IngestionRecordCreate:
    """Generate persistence data for a successful ingestion payload."""

    return IngestionRecordCreate(
        source_id=payload.metadata.source_id,
        adapter_type=payload.metadata.adapter_type,
        status="success",
        duration_ms=payload.metadata.processing_duration_ms,
        correlation_id=payload.metadata.correlation_id,
        payload_metadata=payload.metadata.model_dump(mode="json"),
        validation_summary=validation_summary,
        error_details=None,
    )


def build_error_record(
    *,
    adapter_type: str,
    source_id: str,
    correlation_id: str | None,
    validation_summary: dict[str, Any],
    error_details: dict[str, Any],
    duration_ms: int | None = None,
) -> IngestionRecordCreate:
    """Generate persistence data for a failed ingestion attempt."""

    return IngestionRecordCreate(
        source_id=source_id,
        adapter_type=adapter_type,
        status="error",
        duration_ms=duration_ms,
        correlation_id=correlation_id,
        payload_metadata=None,
        validation_summary=validation_summary,
        error_details=error_details,
    )
