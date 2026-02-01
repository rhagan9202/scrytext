"""Configuration management and reload endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...utils.reload import reload_configuration

router = APIRouter()


@router.post("/reload", summary="Reload configuration")
async def reload_config() -> dict[str, Any]:
    """
    Reload hot-swappable configuration without service restart.

    Reloads:
    - Adapter configurations (PDF, Word, JSON, etc.)
    - Environment-specific settings
    - Feature flags and operational parameters

    Note: Some settings like database URLs require service restart.

    Returns:
        dict: Reload results with status and updated configurations
    """
    result = await reload_configuration()
    return result
