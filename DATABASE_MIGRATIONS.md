# Database Migrations

Scry_Ingestor uses [Alembic](https://alembic.sqlalchemy.org/) to manage database schema
changes for the PostgreSQL persistence layer. This guide explains how to create new
migrations, run them in different environments, and follow zero-downtime practices when
you deploy updates.

## Prerequisites

- `SCRY_DATABASE_URL` must be set to a reachable PostgreSQL instance. The application
  already validates this on startup via `ensure_runtime_configuration`.
- Install dependencies with Poetry (`poetry install`).
- Ensure the database user has privileges to create schemas, tables, indexes, and
  constraints.

## Common Commands

| Task | Command |
|------|---------|
| Create a new revision | `poetry run alembic revision --autogenerate -m "describe change"` |
| Create an empty revision | `poetry run alembic revision -m "manual change"` |
| Run all unapplied migrations | `poetry run alembic upgrade head` |
| Run migrations offline (SQL output only) | `poetry run alembic upgrade --sql head` |
| Downgrade the last migration | `poetry run alembic downgrade -1` |

When autogenerating migrations, review the generated file in `alembic/versions/` and
adjust operations as needed. Keep migrations idempotent and deterministic.

## Zero-downtime Migration Strategy

Production databases must stay online while schema changes are applied. Use the
following pattern when designing migrations:

1. **Prefer additive changes.** Add new columns, constraints, or tables before modifying
   existing structures. Avoid destructive operations in the first step of a rollout.
2. **Backfill data outside the migration.** For large tables, run backfills using a
   Celery task or SQL script after the schema change is in place. Keep DDL migrations
   fast to minimize locks.
3. **Make indexes concurrent.** When adding indexes on populated tables, use
   `op.create_index(..., postgresql_concurrently=True)` and ensure the migration is not
   wrapped in a transaction (see below). Concurrent indexes avoid long exclusive locks.
4. **Use `NOT VALID` constraints.** Add constraints with `postgresql_not_valid=True`
   and validate them in a subsequent migration after data has been cleaned.
5. **Drop safely.** Do not drop columns or tables until you have confirmed the new code
   no longer depends on them. Schedule drops for a later deploy when usage has ceased.

### Allowing concurrent operations

Alembic runs migrations inside a transaction by default. To support operations that
require autocommit (for example, `CREATE INDEX CONCURRENTLY`), set
`transaction_per_migration = True` and explicitly mark the migration block as
`autocommit`:

```python
from alembic import op
from contextlib import suppress
from sqlalchemy import text

# In your migration's upgrade():
with op.get_context().autocommit_block():
    op.create_index(
        "ix_records_correlation_id",
        "ingestion_records",
        ["correlation_id"],
        postgresql_concurrently=True,
    )
```

Only use autocommit blocks for statements that cannot run inside a transaction.

## Deployment Runbook

1. Trigger the release workflow or deploy the container image.
2. Run migrations against the target environment before starting new application pods or
   Celery workers:
   - **Local / CI**: `poetry run alembic upgrade head`
   - **Docker**: `docker compose run --rm api poetry run alembic upgrade head`
   - **Kubernetes**: Prime a Job/CronJob that executes `alembic upgrade head` using the
     same container image as the API/worker deployments.
3. Once migrations succeed, roll out the application, then workers.
4. Monitor database metrics (locks, query time) and application logs for the first few
   minutes.

In the event of a failed deployment, prefer a fix-forward migration. Only run
`alembic downgrade` when you have confirmed that the downgrade path restores a safe
schema state and no new data depends on the forward migration.

## Verification

- `poetry run alembic current` shows the latest migration applied to the database.
- `poetry run alembic history --verbose` lists all revisions with metadata.
- Add integration tests under `tests/models/` to ensure ORM models match the schema
  defined in migrations.
