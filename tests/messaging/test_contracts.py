"""Contract tests ensuring messaging schema compatibility between publisher and consumer."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from fastavro import parse_schema, schemaless_reader, schemaless_writer
from fastavro.validation import validate

from scry_ingestor.messaging.schema import INGESTION_EVENT_SCHEMA, build_ingestion_event_record
from scry_ingestor.schemas.payload import IngestionMetadata, IngestionPayload, ValidationResult


@pytest.fixture
def sample_payload() -> IngestionPayload:
    """Return a representative ingestion payload for contract validation."""

    return IngestionPayload(
        data={"records": 3, "status": "processed"},
        metadata=IngestionMetadata(
            source_id="contract-source",
            adapter_type="JSONAdapter",
            timestamp="2024-10-05T12:00:00Z",
            processing_duration_ms=275,
            processing_mode="local",
            correlation_id="contract-correlation",
        ),
        validation=ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["minor-field-truncated"],
            metrics={"record_count": 3, "throughput": 42.5},
        ),
    )


@pytest.fixture
def parsed_schema() -> Any:
    """Parse and return the Avro schema for ingestion events."""

    return parse_schema(INGESTION_EVENT_SCHEMA)


def test_ingestion_event_record_matches_avro_schema(
    sample_payload: IngestionPayload, parsed_schema: Any
) -> None:
    """Records built from ingestion payloads must satisfy the Avro schema."""

    record = build_ingestion_event_record(sample_payload)
    assert validate(record, parsed_schema) is True


def test_ingestion_event_round_trip_serialization(
    sample_payload: IngestionPayload, parsed_schema: Any
) -> None:
    """Avro schemaless writer/reader should round-trip the record without loss."""

    record = build_ingestion_event_record(sample_payload)

    buffer = BytesIO()
    schemaless_writer(buffer, parsed_schema, record)
    buffer.seek(0)
    decoded = schemaless_reader(buffer, parsed_schema, parsed_schema)

    assert decoded == record


def test_ingestion_event_metrics_are_serialized_as_strings(
    sample_payload: IngestionPayload
) -> None:
    """The metrics map must coerce values to strings for schema compatibility."""

    record = build_ingestion_event_record(sample_payload)

    assert record["metrics"] == {
        "record_count": "3",
        "throughput": "42.5",
    }
    assert all(isinstance(value, str) for value in record["metrics"].values())
