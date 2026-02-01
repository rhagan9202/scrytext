# syntax=docker/dockerfile:1.4
# Optimized multi-stage build for Scry_Ingestor with security hardening

# ============================================================================
# Stage 1: Base Python image with security updates
# ============================================================================
FROM python:3.12-slim-bookworm AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install security updates and minimal runtime dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*


# ============================================================================
# Stage 2: Build dependencies and compile wheels
# ============================================================================
FROM python-base AS builder

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.0 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "poetry==${POETRY_VERSION}"

ENV PATH="${POETRY_HOME}/bin:${PATH}"

WORKDIR /build

# Copy dependency files first (better layer caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies with caching
RUN --mount=type=cache,target=/tmp/poetry_cache \
    poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code
COPY scry_ingestor/ ./scry_ingestor/
COPY README.md ./

# Install the application itself
RUN --mount=type=cache,target=/tmp/poetry_cache \
    poetry install --only-root --no-interaction --no-ansi


# ============================================================================
# Stage 3: Runtime image (minimal, hardened)
# ============================================================================
FROM python-base AS runtime

# Install runtime dependencies only
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with specific UID/GID
RUN groupadd -r -g 1000 scry && \
    useradd -r -u 1000 -g scry -m -s /sbin/nologin scry

WORKDIR /app

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/data /tmp/prometheus \
    && chown -R scry:scry /app /tmp/prometheus

# Copy virtual environment from builder
COPY --from=builder --chown=scry:scry /build/.venv /app/.venv

# Copy application code and configuration
COPY --chown=scry:scry scry_ingestor/ ./scry_ingestor/
COPY --chown=scry:scry config/ ./config/
COPY --chown=scry:scry alembic/ ./alembic/
COPY --chown=scry:scry alembic.ini pyproject.toml ./

# Set runtime environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus" \
    LOG_DIR="/app/logs"

# Security: Remove setuid/setgid bits from executables
RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Switch to non-root user
USER scry

EXPOSE 8000

# OCI standard labels for metadata
LABEL org.opencontainers.image.title="Scry_Ingestor" \
      org.opencontainers.image.description="Data ingestion service" \
      org.opencontainers.image.vendor="Scry" \
      org.opencontainers.image.source="https://github.com/rdhagan92/scrytext"

# Health check with proper timeout
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command - use python -m to ensure PATH is correct
CMD ["python", "-m", "uvicorn", "scry_ingestor.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]


# ============================================================================
# Stage 4: Celery worker variant
# ============================================================================
FROM runtime AS celery-worker

CMD ["python", "-m", "celery", "-A", "scry_ingestor.tasks.celery_app", "worker", \
     "--loglevel=info", "--concurrency=4", "--max-tasks-per-child=1000"]
