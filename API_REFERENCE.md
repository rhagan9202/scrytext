# Scry_Ingestor API Reference

Scry_Ingestor exposes a FastAPI-based HTTP interface for orchestrating data ingestion workflows. The service ships with an auto-generated OpenAPI specification and interactive Swagger UI for exploration and testing.

## Quick Start

| Resource | URL |
| --- | --- |
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

Start the API locally:

```bash
poetry run uvicorn scry_ingestor.api.main:app --reload
```

## Authentication

All ingestion endpoints require an API key sent via the `X-API-Key` header. Configure keys in environment variables (`SCRY_API_KEYS`) or the service will reject requests.

Example header:

```
X-API-Key: your-secret-key
```

## Endpoints

### Health

- `GET /health/live`
- `GET /health/ready`
- Purpose: Liveness and readiness probes for orchestration platforms.

### Ingestion

#### `POST /api/v1/ingest`

Runs the adapter-driven ingestion pipeline.

Request body example:

```json
{
  "adapter_type": "pdf",
  "source_config": {
    "source_id": "invoice-2024-09-15",
    "path": "s3://enterprise-data/documents/invoice.pdf",
    "use_cloud_processing": true,
    "transformation": {
      "extract_metadata": true,
      "extract_tables": false,
      "combine_pages": true
    }
  },
  "correlation_id": "3d0dfb58-3f23-4a7a-9b60-5d0a4ffbc9dd"
}
```

Response example (success):

```json
{
  "status": "success",
  "message": "Data ingested successfully from pdf",
  "payload": {
    "data": {
      "summary": {
        "page_count": 6,
        "total_text_length": 18456
      }
    },
    "metadata": {
      "source_id": "invoice-2024-09-15",
      "adapter_type": "pdf",
      "timestamp": "2025-10-05T10:42:13.581Z",
      "processing_duration_ms": 1290,
      "processing_mode": "cloud",
      "correlation_id": "3d0dfb58-3f23-4a7a-9b60-5d0a4ffbc9dd"
    },
    "validation": {
      "is_valid": true,
      "errors": [],
      "warnings": [],
      "metrics": {
        "text_completeness": 0.98
      }
    }
  },
  "error_details": null
}
```

Error responses return `status: "error"` plus appropriate `message` and `error_details`. Common HTTP codes: 400 for validation failures, 401/403 for authentication failures, 404 when an adapter is not registered, and 500 for unexpected server errors.

#### `GET /api/v1/ingest/adapters`

Lists all registered adapter identifiers:

```json
{
  "adapters": ["json", "csv", "excel", "word", "pdf", "rest", "soup", "beautifulsoup"]
}
```

### Observability

#### `GET /metrics`

Prometheus-compatible metrics endpoint exposing ingestion counts, durations, and error rates.

## Securing the OpenAPI UI

In production, protect the Swagger UI with network controls or authentication middleware. The API key security scheme is fully documented in the OpenAPI spec; clients can generate strongly typed SDKs using the JSON document.

## Generating Client SDKs

Download `openapi.json` and feed it into your preferred generator, for example:

```bash
openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g python \
  -o ./sdks/python
```

## Versioning

The current API version is **v1**. Backwards-incompatible changes will increment the major version and appear under `/api/v2/*` paths.
