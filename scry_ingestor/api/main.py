"""FastAPI application for Scry_Ingestor service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ..exceptions import ScryIngestorError
from ..utils.config import ensure_runtime_configuration, get_settings
from ..utils.logging import setup_logger

logger = setup_logger(__name__, context={"adapter_type": "FastAPI"})


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore
    """Application lifespan context manager for startup/shutdown."""
    # Startup
    ensure_runtime_configuration(get_settings())
    logger.info("Scry_Ingestor API starting up...")
    yield
    # Shutdown
    logger.info("Scry_Ingestor API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Scry_Ingestor API",
    description="Data ingestion service for collecting and processing data from diverse sources",
    version="0.1.0",
    lifespan=lifespan,
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
