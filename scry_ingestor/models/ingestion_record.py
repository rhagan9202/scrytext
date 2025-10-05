"""SQLAlchemy model definitions for ingestion persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IngestionRecord(Base):
    """Database representation of a single ingestion attempt."""

    __tablename__ = "ingestion_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    validation_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""

        return (
            f"<IngestionRecord id={self.id} adapter={self.adapter_type} "
            f"status={self.status} source={self.source_id}>"
        )
