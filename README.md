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

### Prerequisites

- Python 3.10+
- Poetry 1.7.0+
- Docker & Docker Compose (for containerized deployment)

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
    "transformation": {
        "extract_metadata": True,  # Extract author, title, dates, page count
        "extract_tables": True,  # Extract tables as structured data
        "extract_images": False,  # Extract image metadata (not raw images)
        "layout_mode": False,  # Preserve layout in text extraction
        "combine_pages": True,  # Combine all pages into full_text
        "page_separator": "\n\n"
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
csv_options:
  delimiter: ","
  encoding: "utf-8"
validation:
  min_rows: 1
```

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
