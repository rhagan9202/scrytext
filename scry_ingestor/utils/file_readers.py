"""Utility helpers for chunked file reading across adapters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..exceptions import CollectionError
from .logging import setup_logger

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB

logger = setup_logger(__name__)


def _ensure_mapping(options: Mapping[str, Any] | None, context: str) -> dict[str, Any]:
    """Validate that options is a mapping object."""

    if options is None:
        return {}
    if isinstance(options, Mapping):
        return dict(options)

    logger.warning(
        "%s provided as %s is not a mapping (%s); falling back to defaults.",
        options,
        context,
        type(options).__name__,
    )
    return {}


def _normalize_chunk_size(value: Any, *, default: int, context: str) -> int:
    """Return a positive integer chunk size, falling back to default when invalid."""

    if value is None:
        return default

    try:
        chunk_size = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s value '%s'; using default %d bytes.", context, value, default
        )
        return default

    if chunk_size <= 0:
        logger.warning(
            "%s must be greater than zero (received %s); using default %d bytes.",
            context,
            value,
            default,
        )
        return default

    return chunk_size


def _normalize_max_bytes(value: Any | None) -> int | None:
    """Return a validated maximum byte budget if provided."""

    if value is None:
        return None

    try:
        max_bytes = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid max_bytes value '%s'; disabling size limit and using defaults.",
            value,
        )
        return None

    if max_bytes <= 0:
        logger.warning(
            "max_bytes must be greater than zero (received %s); disabling size limit.",
            value,
        )
        return None

    return max_bytes


def _check_unexpected_keys(resolved: dict[str, Any], allowed: set[str], context: str) -> None:
    """Emit a warning when unsupported keys are present in configuration."""

    unexpected = sorted(set(resolved) - allowed)
    if unexpected:
        logger.warning(
            "Ignoring unsupported %s keys: %s", context, ", ".join(unexpected)
        )


def resolve_text_read_options(
    options: Mapping[str, Any] | None,
) -> tuple[int, int | None, str, str]:
    """Parse text-mode read options returning chunk config and decoding choices."""

    resolved = _ensure_mapping(options, "read_options")
    _check_unexpected_keys(
        resolved,
        {"chunk_size", "max_bytes", "encoding", "errors"},
        "read_options",
    )

    chunk_size = _normalize_chunk_size(
        resolved.get("chunk_size"), default=DEFAULT_CHUNK_SIZE, context="chunk_size"
    )
    max_bytes = _normalize_max_bytes(resolved.get("max_bytes"))
    if max_bytes is not None and max_bytes < chunk_size:
        logger.warning(
            "max_bytes (%d) is smaller than chunk_size (%d); reducing chunk_size to match limit.",
            max_bytes,
            chunk_size,
        )
        chunk_size = max_bytes

    raw_encoding = resolved.get("encoding")
    if isinstance(raw_encoding, str) and raw_encoding.strip():
        encoding = raw_encoding.strip()
    else:
        if raw_encoding is not None:
            logger.warning(
                "Invalid encoding value '%s'; falling back to 'utf-8'.", raw_encoding
            )
        encoding = "utf-8"

    raw_errors = resolved.get("errors")
    if isinstance(raw_errors, str) and raw_errors.strip():
        errors = raw_errors.strip()
    else:
        if raw_errors is not None:
            logger.warning(
                "Invalid errors mode '%s'; falling back to 'strict'.", raw_errors
            )
        errors = "strict"

    return chunk_size, max_bytes, encoding, errors


def resolve_binary_read_options(options: Mapping[str, Any] | None) -> tuple[int, int | None]:
    """Parse binary-mode read options returning chunk configuration."""

    resolved = _ensure_mapping(options, "read_options")
    _check_unexpected_keys(resolved, {"chunk_size", "max_bytes"}, "read_options")

    chunk_size = _normalize_chunk_size(
        resolved.get("chunk_size"), default=DEFAULT_CHUNK_SIZE, context="chunk_size"
    )
    max_bytes = _normalize_max_bytes(resolved.get("max_bytes"))
    if max_bytes is not None and max_bytes < chunk_size:
        logger.warning(
            "max_bytes (%d) is smaller than chunk_size (%d); reducing chunk_size to match limit.",
            max_bytes,
            chunk_size,
        )
        chunk_size = max_bytes
    return chunk_size, max_bytes


def read_text_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
    encoding: str,
    errors: str,
) -> str:
    """Read text data from disk using bounded chunked reads."""

    buffer = bytearray()
    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break
                buffer.extend(chunk)
                if max_bytes is not None and len(buffer) > max_bytes:
                    raise CollectionError("File exceeds configured max_bytes limit")
    except OSError as exc:
        raise CollectionError(f"Failed to read file: {exc}") from exc

    try:
        return buffer.decode(encoding, errors=errors)
    except LookupError:
        logger.warning(
            "Unknown encoding '%s'; retrying with UTF-8.", encoding
        )
        try:
            return buffer.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise CollectionError("Failed to decode file with UTF-8 fallback") from exc
    except UnicodeDecodeError:
        logger.warning(
            "Decoding failed using encoding '%s'; retrying with UTF-8 (errors='replace').",
            encoding,
        )
        try:
            return buffer.decode("utf-8", errors="replace")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise CollectionError("Failed to decode file with UTF-8 fallback") from exc


def read_binary_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
) -> bytes:
    """Read binary data from disk using bounded chunked reads."""

    buffer = bytearray()
    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break
                buffer.extend(chunk)
                if max_bytes is not None and len(buffer) > max_bytes:
                    raise CollectionError("File exceeds configured max_bytes limit")
    except OSError as exc:
        raise CollectionError(f"Failed to read file: {exc}") from exc

    return bytes(buffer)
