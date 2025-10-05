"""Alembic environment configuration for Scry_Ingestor."""

from __future__ import annotations

import logging
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context  # type: ignore[import-untyped]
from scry_ingestor.models.base import Base
from scry_ingestor.utils.config import ensure_runtime_configuration, get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


def get_database_url() -> str:
    """Return the database URL from runtime settings, validating critical secrets."""

    settings = get_settings()
    ensure_runtime_configuration(settings)
    database_url = settings.database_url
    assert database_url is not None
    return database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode configured with just a database URL."""

    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an Engine connection."""

    url = get_database_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
