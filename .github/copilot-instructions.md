# Scry_Ingestor - AI Coding Agent Instructions

## Project Overview
Scry_Ingestor is a **data ingestion service** that collects, processes, and standardizes data from diverse sources (structured, unstructured, tabular) for downstream applications. It's designed as both a **Python package** and **Docker container** for flexible deployment.

## Architecture Principles

### Adapter Pattern for Data Sources
- Each data source type gets a dedicated adapter class
- Adapters implement a common interface for `collect()`, `validate()`, and `transform()` methods
- Support both local and cloud-based processing models (configurable per adapter)
- Example: `UnstructuredTextAdapter`, `StructuredJSONAdapter`, `TabularCSVAdapter`

### Standardized Payload Structure
All adapters output payloads with:
- `data`: Processed content (cleaned text, JSON, or pandas DataFrame)
- `metadata`: Provenance info (source, timestamp, processing pipeline)
- `validation`: Data quality metrics and error flags
- Use consistent JSON serialization for non-DataFrame outputs

### Dual Deployment Modes
- **Package mode**: Import as Python library, integrate directly into apps
- **Service mode**: Run as containerized service with REST API (FastAPI) or message queue consumers (Celery + RabbitMQ/Kafka)

## Tech Stack Specifics

### Python Core
- **FastAPI** for REST endpoints (preferred for new APIs)
- **Celery** for async ingestion tasks (use for batch/long-running jobs)
- **Pandas/NumPy** for tabular data manipulation
- **SQLAlchemy** for database interactions (use declarative models)
- **Poetry** for dependency management and packaging (use `pyproject.toml`)

### Cloud Integration
- **AWS S3** for raw data storage
- **AWS Lambda** for serverless extraction (optional)
- **AWS RDS** for metadata persistence

### Orchestration
- **Docker** for containerization (multi-stage builds preferred)
- **Kubernetes** for production scaling (use Helm charts)

### Testing Philosophy
- **pytest** for all testing (unit, integration, end-to-end)
- **Prefer live test data** over mocking - use real adapters with test fixtures
- **Avoid monkeypatching** - design for dependency injection instead
- **No path manipulation** in `conftest.py` - rely on proper package installation
- Store test data in `tests/fixtures/` directory organized by adapter type

## Development Workflows

### Adding New Data Source Adapters
1. Inherit from `BaseAdapter` abstract class
2. Implement required methods: `collect()`, `validate()`, `transform()`
3. Register adapter in `adapters/__init__.py` registry
4. Add corresponding config schema in `config/adapters.yaml`
5. Write pytest tests in `tests/adapters/test_<source>_adapter.py` using live test data

### Package Management with Poetry
- Add dependencies: `poetry add <package>`
- Add dev dependencies: `poetry add --group dev <package>`
- Install environment: `poetry install`
- Build package: `poetry build`
- See README.md for deployment and build commands

### Configuration Management
- Use YAML for adapter configs (in `config/` directory)
- Environment variables override YAML settings (12-factor app pattern)
- Validate configs with Pydantic models on startup

### Error Handling Pattern
- Raise custom exceptions from `exceptions.py` module
- Log errors with structured context (source ID, timestamp, error type)
- Return validation errors in payload's `validation.errors` array (don't fail silently)

## Code Conventions

### File Organization
```
/adapters/          # Data source adapters (one file per source type)
/api/               # FastAPI routes and schemas
/tasks/             # Celery task definitions
/models/            # SQLAlchemy ORM models
/schemas/           # Pydantic validation schemas
/utils/             # Shared utilities (logging, validation helpers)
/config/            # YAML configuration files
/tests/             # Mirror source structure for tests
  /fixtures/        # Live test data organized by adapter type
```

### Naming Conventions
- Adapters: `<SourceType>Adapter` (e.g., `PDFTextAdapter`, `PostgresTableAdapter`)
- API routes: `/api/v1/ingest/<source-type>` (kebab-case)
- Celery tasks: `ingest_<source_type>_task` (snake_case)
- Config files: `<source_type>_adapter.yaml`

### ML Model Integration
- Store model artifacts in S3, load lazily on first use
- Use factory pattern for model loading: `get_extractor_model(config)`
- Cache model instances per worker process (avoid reloading)

## Critical Integration Points

### Message Queue Outputs
- Publish ingestion results to Kafka topic: `scry.ingestion.complete`
- Include correlation ID in messages for tracing
- Use Avro schema registry for downstream compatibility

### API Authentication
- Implement API key validation middleware for all `/api/v1/ingest/*` routes
- Store keys in environment variables or AWS Secrets Manager
- Return 401 for invalid keys, 403 for insufficient permissions

### Monitoring & Observability
- Log all ingestion attempts with: `source_id`, `adapter_type`, `duration_ms`, `status`
- Export Prometheus metrics: ingestion rate, error rate, processing time
- Use correlation IDs across log entries for request tracing

---
**Note**: This is an actively developed project. Update these instructions when architectural patterns change or new conventions emerge.
