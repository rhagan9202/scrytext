# Multi-stage build for optimal image size
FROM python:3.10-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.0 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1

RUN pip install --no-cache-dir poetry==${POETRY_VERSION}

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies only (leverage Docker layer caching)
RUN poetry install --no-root --only main --no-interaction --no-ansi


# Runtime stage
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 scry && \
    chown -R scry:scry /app

# Copy virtual environment from builder
COPY --from=builder --chown=scry:scry /app/.venv /app/.venv

# Copy application code and runtime assets
COPY --chown=scry:scry scry_ingestor/ ./scry_ingestor/
COPY --chown=scry:scry config/ ./config/
COPY --chown=scry:scry alembic/ ./alembic/
COPY --chown=scry:scry alembic.ini ./alembic.ini

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus"

RUN mkdir -p "${PROMETHEUS_MULTIPROC_DIR}" && chown -R scry:scry "${PROMETHEUS_MULTIPROC_DIR}"

# Switch to non-root user
USER scry

# Expose port for FastAPI
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys, urllib.request, socket; from urllib.error import URLError, HTTPError; url='http://127.0.0.1:8000/health';\ntry:\n    with urllib.request.urlopen(url, timeout=5) as response:\n        sys.exit(0 if response.status == 200 else 1)\nexcept (URLError, HTTPError, socket.timeout):\n    sys.exit(1)"

# Default command to run FastAPI with uvicorn
CMD ["uvicorn", "scry_ingestor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
