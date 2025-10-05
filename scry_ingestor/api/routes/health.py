"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Status message indicating service is healthy
    """
    return {"status": "healthy", "service": "scry_ingestor"}
