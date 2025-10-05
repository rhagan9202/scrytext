# Scry_Ingestor

**Data ingestion service** that collects, processes, and standardizes data from diverse sources (structured, unstructured, tabular) for downstream applications.

## Features

- 🔌 **Adapter Pattern** - Pluggable adapters for different data sources
- 📦 **Standardized Payloads** - Consistent data structure with metadata and validation
- 🚀 **Dual Deployment** - Use as Python package or containerized service
- ⚡ **Async Processing** - FastAPI for REST endpoints, Celery for background tasks
- 🔍 **Data Validation** - Built-in validation with quality metrics
- 📊 **Multiple Formats** - Support for JSON, CSV, text, and custom formats
- 🛡️ **Type Safety** - Full Pydantic validation throughout

## Quick Start

## Documentation

- [API Reference](./API_REFERENCE.md) – Endpoint catalog, authentication, and example payloads.
- [Deployment Guide](./DEPLOYMENT_GUIDE.md) – Step-by-step instructions for local, container, and cloud environments.
- [Performance Characteristics](./PERFORMANCE.md) – Throughput guidance, scaling strategies, and tuning tips.

### Prerequisites

- Python 3.10+
- Poetry 1.7.0+
- Docker & Docker Compose (for containerized deployment)

### Configuration

Scry_Ingestor reads critical secrets (database, Redis, API keys) from environment
variables. Copy `.env.example` to `.env` and adjust the values before running the
service locally or via Docker Compose:

```bash
cp .env.example .env
# update database credentials, API keys, etc.
```

> **Required values**
>
> - `SCRY_DATABASE_URL` – PostgreSQL connection string (Compose uses the
>   Postgres service by default)
> - `SCRY_API_KEYS` – comma-separated list of API keys accepted by the REST API

The application validates these settings on startup and will exit if they are
missing, preventing partially configured deployments.

### Installation

#### As a Python Package

```bash
# Clone the repository
git clone https://github.com/yourusername/scrytext.git
cd scrytext

# Install with Poetry
poetry install

# Activate the virtual environment
poetry shell
```

#### With Docker

```bash
# Build and start all services
docker-compose up --build

# API will be available at http://localhost:8000
```

## Development Workflows

### Running the API Locally

```bash
# With Poetry
poetry run uvicorn scry_ingestor.api.main:app --reload --host 0.0.0.0 --port 8000

# With Docker Compose
docker-compose up api
```

### Running Tests

```bash
# Run all tests with coverage
poetry run pytest

# Run specific test file
poetry run pytest tests/adapters/test_json_adapter.py

# Run with verbose output
poetry run pytest -v

# Run and watch for changes
poetry run pytest-watch
```

### Code Quality

```bash
# Format code with Black
poetry run black scry_ingestor/ tests/

# Lint with Ruff
poetry run ruff check scry_ingestor/ tests/

# Type checking with mypy
poetry run mypy scry_ingestor/
```

### Building the Package

```bash
# Build wheel and sdist
poetry build

# Output will be in dist/
```

### Building Docker Images

```bash
# Build production image
docker build -t scry-ingestor:latest .

# Build with specific tag
docker build -t scry-ingestor:v0.1.0 .

# Multi-platform build (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 -t scry-ingestor:latest .
```

### Database Migrations

- Generate schema changes with Alembic and review the resulting files under
  `alembic/versions/` before committing.
- Apply migrations locally and in CI with `poetry run alembic upgrade head` after
  exporting the `SCRY_DATABASE_URL` environment variable.
- Follow the zero-downtime checklist in [`DATABASE_MIGRATIONS.md`](./DATABASE_MIGRATIONS.md)
  for production rollouts, including concurrent indexes and staged destructive changes.

### Container Health, Metrics & Scanning

- The container baked health check calls `GET /health` on port 8000. The same probe is
  wired into `docker-compose.yml`, enabling orchestrators to track readiness and liveness.
- Prometheus metrics are exposed at `GET /metrics` on port 8000, and the compose service
  includes `prometheus.io/*` labels for auto-discovery. Multiprocess metrics are enabled
  via `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus` in the image.
- The build context is trimmed with `.dockerignore` so only runtime assets reach the
  final layer; migrate any new required files into the explicit COPY list before relying
  on them at runtime.
- Run ad-hoc vulnerability scans on images before publishing:

```bash
# Scan the local image (adjust tag/registry as needed)
trivy image scry-ingestor:latest

# Compare SBOMs and CVEs using Docker Scout
docker scout cves scry-ingestor:latest
```

- CI executes nightly `trivy` and `pip-audit` checks (see `ops-nightly.yml`), but manual
  scans are encouraged before promoting images to production registries.

## CI/CD & Operations

Scry_Ingestor uses GitHub Actions to coordinate quality gates, packaging, and operational checks. The following workflows live in `.github/workflows/`:

- **`ci.yml`** – Runs on pushes to `main`/`develop` and on pull requests. Executes Ruff, Black, MyPy, and pytest across Python 3.10 and 3.12 using Poetry-managed virtualenvs.
- **`docker.yml`** – Builds the multi-stage production image with Buildx. Images are pushed to `ghcr.io/<owner>/scry-ingestor` on `main` or semver tag pushes, and built (without publishing) for pull requests.
- **`release.yml`** – Publishes Poetry artifacts to PyPI when a tag prefixed with `v` is pushed. Requires the repository secret `PYPI_TOKEN`. The workflow also uploads the built distributions as artifacts.
- **`codeql.yml`** – Performs static analysis with CodeQL on pushes, pull requests, and a weekly schedule.
- **`dependency-review.yml`** – Adds automated dependency change reviews to pull requests targeting `main` or `develop`, failing the build on new high-severity advisories.
- **`ops-nightly.yml`** – Nightly scheduled job that runs `pip-audit` against Poetry dependencies and scans the Docker image with Trivy for critical/high vulnerabilities. Fails the job if these checks find actionable issues.

### Required secrets & environments

| Workflow | Secret / Setting | Purpose |
|----------|------------------|---------|
| `docker.yml` | `GITHUB_TOKEN` (built-in) | Authenticates with GHCR for image pushes. |
| `release.yml` | `PYPI_TOKEN` | PyPI publishing credentials (recommend storing in a protected `pypi` environment). |
| `ops-nightly.yml` | *(none required)* | Uses public registries; optionally add `TRIVY_USERNAME`/`TRIVY_PASSWORD` when scanning private bases. |

To tailor pipelines for additional platforms (e.g., AWS ECR, Slack notifications), add the necessary secrets to the repository or to [GitHub Environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) and update the workflows accordingly.

## Usage Examples

### Using the JSONAdapter

```python
from scry_ingestor.adapters.json_adapter import JSONAdapter

# Configure adapter
config = {
    "source_id": "my-json-source",
    "source_type": "file",
    "path": "/path/to/data.json",
    "use_cloud_processing": False,
  "read_options": {
    "chunk_size": 64 * 1024,  # Stream 64KB per read
    "max_bytes": 5 * 1024 * 1024,  # Fail fast if file exceeds 5MB
  },
}

# Create adapter and process data
adapter = JSONAdapter(config)
payload = await adapter.process()

# Access the data
print(payload.data)  # Parsed JSON dict
print(payload.metadata)  # Processing metadata
print(payload.validation)  # Validation results
```

### Using the CSVAdapter

```python
from scry_ingestor.adapters.csv_adapter import CSVAdapter

# Configure adapter
config = {
    "source_id": "my-csv-source",
    "source_type": "file",
    "path": "/path/to/data.csv",
    "use_cloud_processing": False,
  "read_options": {
    "chunk_size": 128 * 1024,
    "max_bytes": 50 * 1024 * 1024,
  },
}

# Create adapter and process data
adapter = CSVAdapter(config)
payload = await adapter.process()

# Access the data as pandas DataFrame
print(payload.data)  # pandas DataFrame
print(len(payload.data))  # Number of rows
print(payload.validation.metrics)  # Row/column counts
```

### Using the ExcelAdapter

```python
from scry_ingestor.adapters.excel_adapter import ExcelAdapter

# Configure adapter
config = {
    "source_id": "my-excel-source",
    "source_type": "file",
    "path": "/path/to/data.xlsx",
    "sheet_name": "Sheet1",  # Or use 0 for first sheet
    "use_cloud_processing": False,
  "read_options": {
    "chunk_size": 512 * 1024,
    "max_bytes": 75 * 1024 * 1024,
  },
}

# Create adapter and process data
adapter = ExcelAdapter(config)
payload = await adapter.process()

# Access the data as pandas DataFrame
print(payload.data)  # pandas DataFrame
print(payload.data.columns.tolist())  # Column names
```

### Using the WordAdapter

```python
from scry_ingestor.adapters.word_adapter import WordAdapter

# Configure adapter (.docx files only)
config = {
    "source_id": "my-word-source",
    "source_type": "file",
    "path": "/path/to/document.docx",  # Must be .docx format
    "use_cloud_processing": False,
  "read_options": {
    "chunk_size": 512 * 1024,
    "max_bytes": 25 * 1024 * 1024,
  },
    "transformation": {
        "extract_metadata": True,  # Extract author, title, etc.
        "extract_tables": True,  # Extract tables as structured data
        "strip_whitespace": True,
        "paragraph_separator": "\n"
    }
}

# Create adapter and process data
adapter = WordAdapter(config)
payload = await adapter.process()

# Access the extracted text and metadata
print(payload.data["text"])  # Full document text
print(payload.data["metadata"]["author"])  # Document author
print(payload.data["metadata"]["title"])  # Document title
if "tables" in payload.data:
    print(payload.data["tables"])  # Extracted tables
```

**Note:** WordAdapter supports `.docx` files only (Office 2007+). If you have legacy `.doc` files:
- Convert using Microsoft Word: File > Save As > Word Document (.docx)
- Convert using LibreOffice: `libreoffice --headless --convert-to docx file.doc`
- Convert using online tools: CloudConvert, Zamzar, or Google Docs

### Using the PDFAdapter

```python
from scry_ingestor.adapters.pdf_adapter import PDFAdapter

# Configure adapter (uses pdfplumber + pymupdf for best results)
config = {
    "source_id": "my-pdf-source",
    "source_type": "file",
    "path": "/path/to/document.pdf",
    "use_cloud_processing": False,
  "read_options": {
    "chunk_size": 1024 * 1024,
    "max_bytes": 150 * 1024 * 1024,
  },
    "transformation": {
        "extract_metadata": True,  # Extract author, title, dates, page count
        "extract_tables": True,  # Extract tables as structured data
        "extract_images": False,  # Extract image metadata (not raw images)
        "layout_mode": False,  # Preserve layout in text extraction
        "combine_pages": True,  # Combine all pages into full_text
    "page_separator": "\n\n",
    "max_text_chars_per_page": None  # Trim page text payload (int) to cap size
    }
}

# Create adapter and process data
adapter = PDFAdapter(config)
payload = await adapter.process()

# Access the extracted content
print(payload.data["full_text"])  # All text combined
print(payload.data["metadata"]["author"])  # Document author
print(payload.data["metadata"]["page_count"])  # Number of pages
print(payload.data["summary"]["total_tables"])  # Tables found

# Access per-page data
for page in payload.data["pages"]:
    print(f"Page {page['page_number']}: {page['text'][:100]}...")
    if "tables" in page:
        print(f"  Found {len(page['tables'])} tables on this page")
```

**Features:**
- Best-in-class table extraction using pdfplumber
- High-performance text extraction
- Comprehensive metadata (author, title, creator, dates)
- Multi-page document support
- Layout-aware text extraction option
- Image detection and metadata
- Per-page processing for large documents
- Optional per-page text trimming to control payload size

**Table extraction guidance:**
- Enable `transformation.extract_tables` only when you need structured table output—each table is returned as a 2D list per page.
- Vector-based or text-based PDFs yield the cleanest tables. Scanned tables require OCR plus grid lines for reliable results.
- Adjust `table_settings.vertical_strategy` / `horizontal_strategy` when tables lack ruling lines (`"text"` works well for whitespace-aligned tables).
- Tune `snap_tolerance` and `join_tolerance` for skewed scans. Increase values for noisy documents; lower them to avoid merging unrelated cells.
- Use the `page_range` option to focus extraction on table-heavy sections and speed up processing.

**OCR prerequisites (scanned PDFs):**
- Install the Tesseract engine on the host (Linux: `sudo apt install tesseract-ocr`; macOS: `brew install tesseract`).
- Add any additional language packs you need (for example, `tesseract-ocr-spa` on Debian/Ubuntu).
- Ensure the `tesseract` binary is on the PATH for the service container or runtime user.
- Set the `ocr.enabled` flag in `config/pdf_adapter.yaml` or the runtime config to `true` and choose the correct language code.
- Expect slower processing and slightly larger payloads when OCR is enabled; scanned pages without OCR continue to raise validation warnings.

**Payload trimming:**
- Set `transformation.max_text_chars_per_page` to cap the number of characters stored per page.
- Trimmed pages include `text_truncated`, `text_original_length`, and `text_trimmed_characters` metadata for downstream auditing.
- Summary statistics expose `trimmed_pages` and `trimmed_characters` to monitor how often trimming occurs.

## Troubleshooting

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `401 Unauthorized` from `/api/v1/ingest` | Missing `X-API-Key` header or key not configured | Add header with a value present in `SCRY_API_KEYS`. Reload app after changing keys. |
| `SCRY_DATABASE_URL is required` during startup | Database URL not set | Export `SCRY_DATABASE_URL` or provide it in `.env` before launching the API. |
| `AdapterNotFoundError` in responses | Adapter name typo or adapter not registered | Run `GET /api/v1/ingest/adapters` to list supported adapters and update request payload. |
| Celery worker exits with broker errors | Incorrect `SCRY_BROKER_URL` | Verify broker is reachable; regenerate connection string (e.g., `redis://host:6379/0`). |
| Large PDF ingestions timeout | `max_bytes`/`max_text_chars_per_page` not tuned | Increase limits or enable streaming options in the adapter config. |
| Prometheus metrics missing | Metrics endpoint not scraped | Confirm `/metrics` is exposed and Prometheus scrape config targets the service. |

Need more help? Open an issue or reach out to the platform team with logs and correlation IDs.

### Using the REST API

```bash
# Health check
curl http://localhost:8000/health

# List available adapters
curl http://localhost:8000/api/v1/ingest/adapters

# Ingest JSON data
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_type": "json",
    "source_config": {
      "source_id": "api-test",
      "source_type": "string",
      "data": "{\"name\": \"test\", \"value\": 42}"
    }
  }'

# Ingest CSV data
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_type": "csv",
    "source_config": {
      "source_id": "csv-test",
      "source_type": "file",
      "path": "/data/sample.csv"
    }
  }'

# Ingest Excel data
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_type": "excel",
    "source_config": {
      "source_id": "excel-test",
      "source_type": "file",
      "path": "/data/sample.xlsx",
      "sheet_name": "Products"
    }
  }'

# Ingest Word document
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_type": "word",
    "source_config": {
      "source_id": "word-test",
      "source_type": "file",
      "path": "/data/document.docx"
    }
  }'
```

### Creating a Custom Adapter

```python
from scry_ingestor.adapters.base import BaseAdapter
from scry_ingestor.schemas.payload import ValidationResult

class MyCustomAdapter(BaseAdapter):
    async def collect(self) -> Any:
        # Implement data collection logic
        return raw_data
    
    async def validate(self, raw_data: Any) -> ValidationResult:
        # Implement validation logic
        return ValidationResult(is_valid=True, errors=[], warnings=[], metrics={})
    
    async def transform(self, raw_data: Any) -> Any:
        # Implement transformation logic
        return transformed_data

# Register the adapter
from scry_ingestor.adapters import register_adapter
register_adapter("my-custom", MyCustomAdapter)
```

## Project Structure

```
scry_ingestor/
├── adapters/          # Data source adapters
│   ├── base.py        # BaseAdapter abstract class
│   ├── json_adapter.py
│   └── __init__.py    # Adapter registry
├── api/               # FastAPI application
│   ├── main.py        # App setup and middleware
│   └── routes/        # API endpoints
├── schemas/           # Pydantic validation schemas
├── utils/             # Shared utilities (logging, config)
├── tasks/             # Celery task definitions
├── models/            # SQLAlchemy ORM models
└── exceptions.py      # Custom exceptions

tests/
├── adapters/          # Adapter tests
├── api/               # API tests
└── fixtures/          # Live test data
```

## Configuration

### Philosophy: Defaults vs. Runtime Data

**Config files contain defaults and options**, not runtime data sources:

```yaml
# config/csv_adapter.yaml - Default settings
use_cloud_processing: false
read_options:
  chunk_size: 1048576  # Stream 1MB at a time from disk
  max_bytes: null      # Set to guard against unexpectedly large files
  encoding: "utf-8"
  errors: "strict"
csv_options:
  delimiter: ","
  skip_blank_lines: true
  header: 0
validation:
  min_rows: 1
```

`read_options` apply to every file-based adapter (JSON, CSV, Excel, Word, PDF) so you can stream uploads in predictable chunks and fail fast when a payload exceeds safety limits. Override them per request to tighten limits for user uploads or expand limits for trusted batch jobs.

**File paths and data sources are provided at runtime** via API or code:

```python
# Good: Pass paths at runtime
config = {
    "source_id": "my-data",
    "source_type": "file",
    "path": "/runtime/path/to/data.csv",  # Runtime decision
}
adapter = CSVAdapter(config)
```

```bash
# Good: API caller specifies the file
curl -X POST http://localhost:8000/api/v1/ingest \
  -d '{"adapter_type": "csv", "source_config": {"source_id": "test", "path": "/data/file.csv"}}'
```

This separation enables:
- **Portability**: Same config works across dev/staging/prod
- **Flexibility**: Users specify data sources dynamically
- **Security**: Paths not hardcoded in version control
- **Multi-tenancy**: Different users/requests use different files

### Environment Variable Overrides

Environment variables override YAML settings using `SCRY_` prefix:

```bash
export SCRY_AWS__REGION=us-west-2
export SCRY_LOG_LEVEL=DEBUG
export SCRY_CSV_OPTIONS__DELIMITER=";"
```

Example: Override CSV delimiter globally without changing YAML files.

## Deployment

### Docker Deployment

```bash
# Production deployment with docker-compose
docker-compose -f docker-compose.prod.yml up -d

# Scale workers
docker-compose up --scale worker=3
```

### Kubernetes Deployment

```bash
# Using Helm (chart not included in this repo)
helm install scry-ingestor ./helm-chart \
  --set image.tag=v0.1.0 \
  --set replicaCount=3
```

### Package Deployment

```bash
# Build and publish to PyPI
poetry build
poetry publish

# Install from PyPI
pip install scry-ingestor
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SCRY_LOG_LEVEL` | Logging level | `INFO` |
| `SCRY_AWS__REGION` | AWS region | `us-east-1` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend | `redis://localhost:6379/0` |

## Contributing

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for development guidelines and architectural patterns.

## License

[Add your license here]

## Support

[Add contact/support information]
