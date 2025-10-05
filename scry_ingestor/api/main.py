"""FastAPI application for Scry_Ingestor service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ..exceptions import ScryIngestorError
from ..utils.config import ensure_runtime_configuration
from ..utils.logging import setup_logger

logger = setup_logger(__name__, context={"adapter_type": "FastAPI"})


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore
    """Application lifespan context manager for startup/shutdown."""
    # Startup
    settings = ensure_runtime_configuration()
    logger.info(
        "Scry_Ingestor API starting up...",
        extra={"environment": settings.environment},
    )
    yield
    # Shutdown
    logger.info("Scry_Ingestor API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Scry_Ingestor API",
    description="""
## Data Ingestion Service

Scry_Ingestor is a comprehensive data ingestion service that collects,
processes, and standardizes data from diverse sources including:
- **Structured data**: JSON, CSV, Excel files
- **Unstructured data**: PDF documents, Word files
- **Web content**: HTML scraping, REST APIs

### Key Features
- 🔄 **Adapter Pattern**: Pluggable adapters for different data source types
- 📊 **Standardized Output**: Consistent payload structure across all adapters
- 🔐 **API Key Authentication**: Secure access control
- 📈 **Observability**: Built-in metrics, logging, and monitoring
- ⚡ **Async Processing**: High-performance async ingestion pipeline
- 🛡️ **Error Handling**: Comprehensive validation and error reporting

### Authentication
All ingestion endpoints require API key authentication via the `X-API-Key` header.
    """,
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "Scry_Ingestor Support",
        "url": "https://github.com/your-org/scry-ingestor",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    servers=[
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        },
        {
            "url": "https://api.scry-ingestor.example.com",
            "description": "Production server"
        }
    ],
    openapi_tags=[
        {
            "name": "health",
            "description": "Health check endpoints for service monitoring"
        },
        {
            "name": "ingestion",
            "description": "Data ingestion endpoints for processing various data sources"
        },
        {
            "name": "monitoring",
            "description": "Metrics and observability endpoints"
        }
    ]
)


# Global exception handler
@app.exception_handler(ScryIngestorError)
async def scry_exception_handler(request: Request, exc: ScryIngestorError) -> JSONResponse:
    """Handle custom Scry_Ingestor exceptions."""
    correlation_id = request.headers.get("x-correlation-id") or "-"
    logger.error(
        "ScryIngestorError: %s",
        exc,
        extra={
            "path": request.url.path,
            "correlation_id": correlation_id,
            "status": "error",
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": str(exc), "error_type": exc.__class__.__name__},
    )


# Import routers
from .routes import health, ingestion, metrics  # noqa: E402

app.include_router(health.router, tags=["health"])
app.include_router(ingestion.router, prefix="/api/v1", tags=["ingestion"])
app.include_router(metrics.router, tags=["monitoring"])
