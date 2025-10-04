"""FastAPI application for Scry_Ingestor service."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ..exceptions import ScryIngestorError
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore
    """Application lifespan context manager for startup/shutdown."""
    # Startup
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
    logger.error(f"ScryIngestorError: {exc}", extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": str(exc), "error_type": exc.__class__.__name__},
    )


# Import routers
from .routes import health, ingestion  # noqa: E402

app.include_router(health.router, tags=["health"])
app.include_router(ingestion.router, prefix="/api/v1", tags=["ingestion"])
