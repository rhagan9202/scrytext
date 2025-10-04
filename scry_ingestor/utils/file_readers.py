"""Utility helpers for chunked file reading across adapters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..exceptions import CollectionError

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB


def _ensure_mapping(options: Mapping[str, Any] | None, context: str) -> Mapping[str, Any]:
    """Validate that options is a mapping object."""

    if options is None:
        return {}
    if isinstance(options, Mapping):
        return options
    raise CollectionError(f"{context} must be a mapping of option names to values")


def _normalize_chunk_size(value: Any, context: str) -> int:
    """Return a positive integer chunk size."""

    try:
        chunk_size = int(value)
    except (TypeError, ValueError) as exc:
        raise CollectionError(f"{context} must be an integer value") from exc
    if chunk_size <= 0:
        raise CollectionError(f"{context} must be greater than zero")
    return chunk_size


def _normalize_max_bytes(value: Any | None) -> int | None:
    """Return a validated maximum byte budget if provided."""

    if value is None:
        return None
    try:
        max_bytes = int(value)
    except (TypeError, ValueError) as exc:
        raise CollectionError("max_bytes must be an integer value") from exc
    if max_bytes <= 0:
        raise CollectionError("max_bytes must be greater than zero")
    return max_bytes


def resolve_text_read_options(
    options: Mapping[str, Any] | None,
) -> tuple[int, int | None, str, str]:
    """Parse text-mode read options returning chunk config and decoding choices."""

    resolved = _ensure_mapping(options, "read_options")

    chunk_size = _normalize_chunk_size(resolved.get("chunk_size", DEFAULT_CHUNK_SIZE), "chunk_size")
    max_bytes = _normalize_max_bytes(resolved.get("max_bytes"))
    encoding = str(resolved.get("encoding", "utf-8"))
    errors = str(resolved.get("errors", "strict"))

    return chunk_size, max_bytes, encoding, errors


def resolve_binary_read_options(options: Mapping[str, Any] | None) -> tuple[int, int | None]:
    """Parse binary-mode read options returning chunk configuration."""

    resolved = _ensure_mapping(options, "read_options")
    chunk_size = _normalize_chunk_size(resolved.get("chunk_size", DEFAULT_CHUNK_SIZE), "chunk_size")
    max_bytes = _normalize_max_bytes(resolved.get("max_bytes"))
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
    except LookupError as exc:
        raise CollectionError(f"Unknown encoding requested: {encoding}") from exc
    except UnicodeDecodeError as exc:
        raise CollectionError("Failed to decode file with provided encoding") from exc


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
