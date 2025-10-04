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
COPY pyproject.toml ./

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

# Copy application code
COPY --chown=scry:scry scry_ingestor/ ./scry_ingestor/
COPY --chown=scry:scry config/ ./config/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER scry

# Expose port for FastAPI
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Default command to run FastAPI with uvicorn
CMD ["uvicorn", "scry_ingestor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
