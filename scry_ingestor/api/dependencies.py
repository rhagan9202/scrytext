"""Shared FastAPI dependencies."""

from __future__ import annotations

import secrets

from fastapi import (
    HTTPException,
    Security,
    status,
)
from fastapi.security import APIKeyHeader

from ..utils.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(x_api_key: str | None = Security(api_key_header)) -> str:
    """Validate the provided API key against configured secrets."""

    settings = get_settings()
    configured_keys = settings.api_keys

    if not configured_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API authentication is not configured.",
        )

    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
        )

    for candidate in configured_keys:
        if secrets.compare_digest(x_api_key, candidate):
            return candidate

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key.",
    )
