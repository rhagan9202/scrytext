"""Utility helpers for chunked file reading across adapters."""

from __future__ import annotations

import asyncio
import codecs
from collections.abc import AsyncIterator, Iterator, Mapping
from pathlib import Path
from typing import Any

from ..exceptions import CollectionError
from .logging import setup_logger

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB

logger = setup_logger(__name__, context={"adapter_type": "FileReaders"})


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


def _initialize_incremental_decoder(
    encoding: str,
    errors: str,
) -> tuple[codecs.IncrementalDecoder, str, str]:
    """Create an incremental decoder, falling back to UTF-8 when unknown."""

    chosen_encoding = encoding
    chosen_errors = errors
    try:
        decoder_cls = codecs.getincrementaldecoder(chosen_encoding)
    except LookupError:
        logger.warning(
            "Unknown encoding '%s'; falling back to 'utf-8'.",
            encoding,
        )
        chosen_encoding = "utf-8"
        chosen_errors = "strict"
        decoder_cls = codecs.getincrementaldecoder(chosen_encoding)
    decoder = decoder_cls(errors=chosen_errors)
    return decoder, chosen_encoding, chosen_errors


def _decode_chunk_with_fallback(
    decoder: codecs.IncrementalDecoder,
    chunk: bytes,
    *,
    state: dict[str, str],
) -> tuple[str, codecs.IncrementalDecoder]:
    """Decode a chunk of bytes, retrying with UTF-8 replacement on failure."""

    try:
        return decoder.decode(chunk), decoder
    except UnicodeDecodeError:
        logger.warning(
            "Decoding failed using encoding '%s'; retrying with UTF-8 (errors='replace').",
            state.get("encoding", "unknown"),
        )
        state["encoding"] = "utf-8"
        state["errors"] = "replace"
        fallback_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        return fallback_decoder.decode(chunk), fallback_decoder


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


def stream_text_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
    encoding: str,
    errors: str,
) -> Iterator[str]:
    """Yield decoded text chunks without loading the entire file into memory."""

    decoder, active_encoding, active_errors = _initialize_incremental_decoder(encoding, errors)
    state = {"encoding": active_encoding, "errors": active_errors}
    bytes_read = 0

    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break

                bytes_read += len(chunk)
                if max_bytes is not None and bytes_read > max_bytes:
                    raise CollectionError("File exceeds configured max_bytes limit")

                decoded, decoder = _decode_chunk_with_fallback(decoder, chunk, state=state)
                if decoded:
                    yield decoded

            trailing = decoder.decode(b"", final=True)
            if trailing:
                yield trailing
    except OSError as exc:
        raise CollectionError(f"Failed to read file: {exc}") from exc


def stream_binary_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
) -> Iterator[bytes]:
    """Yield binary chunks from disk, respecting max_bytes guardrails."""

    bytes_read = 0
    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if max_bytes is not None and bytes_read > max_bytes:
                    raise CollectionError("File exceeds configured max_bytes limit")
                yield bytes(chunk)
    except OSError as exc:
        raise CollectionError(f"Failed to read file: {exc}") from exc


async def async_stream_text_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
    encoding: str,
    errors: str,
) -> AsyncIterator[str]:
    """Asynchronously yield decoded text chunks using a background thread."""

    decoder, active_encoding, active_errors = _initialize_incremental_decoder(encoding, errors)
    state = {"encoding": active_encoding, "errors": active_errors}
    bytes_read = 0
    loop = asyncio.get_running_loop()

    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = await loop.run_in_executor(None, file_handle.read, chunk_size)
                if not chunk:
                    break

                bytes_read += len(chunk)
                if max_bytes is not None and bytes_read > max_bytes:
                    raise CollectionError("File exceeds configured max_bytes limit")

                decoded, decoder = _decode_chunk_with_fallback(decoder, chunk, state=state)
                if decoded:
                    yield decoded

            trailing = decoder.decode(b"", final=True)
            if trailing:
                yield trailing
    except OSError as exc:
        raise CollectionError(f"Failed to read file: {exc}") from exc


async def async_stream_binary_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
) -> AsyncIterator[bytes]:
    """Asynchronously yield binary chunks using a background executor."""

    bytes_read = 0
    loop = asyncio.get_running_loop()

    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = await loop.run_in_executor(None, file_handle.read, chunk_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if max_bytes is not None and bytes_read > max_bytes:
                    raise CollectionError("File exceeds configured max_bytes limit")
                yield bytes(chunk)
    except OSError as exc:
        raise CollectionError(f"Failed to read file: {exc}") from exc


def read_text_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
    encoding: str,
    errors: str,
) -> str:
    """Read text data from disk using bounded chunked reads."""

    return "".join(
        stream_text_file(
            file_path,
            chunk_size=chunk_size,
            max_bytes=max_bytes,
            encoding=encoding,
            errors=errors,
        )
    )


def read_binary_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
) -> bytes:
    """Read binary data from disk using bounded chunked reads."""

    return b"".join(
        stream_binary_file(
            file_path,
            chunk_size=chunk_size,
            max_bytes=max_bytes,
        )
    )


async def async_read_text_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
    encoding: str,
    errors: str,
) -> str:
    """Asynchronously read text data by consuming the streaming generator."""

    parts: list[str] = []
    async for piece in async_stream_text_file(
        file_path,
        chunk_size=chunk_size,
        max_bytes=max_bytes,
        encoding=encoding,
        errors=errors,
    ):
        parts.append(piece)
    return "".join(parts)


async def async_read_binary_file(
    file_path: str | Path,
    *,
    chunk_size: int,
    max_bytes: int | None,
) -> bytes:
    """Asynchronously read binary data using the streaming helper."""

    parts: list[bytes] = []
    async for chunk in async_stream_binary_file(
        file_path,
        chunk_size=chunk_size,
        max_bytes=max_bytes,
    ):
        parts.append(chunk)
    return b"".join(parts)
