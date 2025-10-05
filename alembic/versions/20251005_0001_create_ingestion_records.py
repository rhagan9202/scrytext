"""Create ingestion_records table for ingestion persistence."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op as alembic_op  # type: ignore[import-untyped]

revision = "20251005_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the ingestion_records table and supporting indexes."""

    alembic_op.create_table(
        "ingestion_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("adapter_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("payload_metadata", sa.JSON(), nullable=True),
        sa.Column("validation_summary", sa.JSON(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    alembic_op.create_index(
        "ix_ingestion_records_adapter_type",
        "ingestion_records",
        ["adapter_type"],
    )
    alembic_op.create_index(
        "ix_ingestion_records_status",
        "ingestion_records",
        ["status"],
    )
    alembic_op.create_index(
        "ix_ingestion_records_correlation_id",
        "ingestion_records",
        ["correlation_id"],
    )


def downgrade() -> None:
    """Drop ingestion_records table and related indexes."""

    alembic_op.drop_index("ix_ingestion_records_correlation_id", table_name="ingestion_records")
    alembic_op.drop_index("ix_ingestion_records_status", table_name="ingestion_records")
    alembic_op.drop_index("ix_ingestion_records_adapter_type", table_name="ingestion_records")
    alembic_op.drop_table("ingestion_records")
