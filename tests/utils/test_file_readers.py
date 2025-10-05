"""Tests for streaming file reader helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scry_ingestor.exceptions import CollectionError
from scry_ingestor.utils.file_readers import (
    async_read_binary_file,
    async_read_text_file,
    async_stream_binary_file,
    async_stream_text_file,
    stream_binary_file,
    stream_text_file,
)


def test_stream_text_file_preserves_content(tmp_path: Path) -> None:
    """Streaming text reads should reconstruct the original content."""

    base_dir = tmp_path / "files"
    base_dir.mkdir()
    file_path = base_dir / "sample.txt"
    content = "The quick brown fox jumps over the lazy dog.\n" * 8
    file_path.write_text(content, encoding="utf-8")

    chunks = list(
        stream_text_file(
            file_path,
            chunk_size=32,
            max_bytes=None,
            encoding="utf-8",
            errors="strict",
        )
    )

    assert "".join(chunks) == content
    assert any(chunk for chunk in chunks)


def test_stream_binary_file_respects_max_bytes(tmp_path: Path) -> None:
    """Binary streaming should raise when exceeding the configured byte budget."""

    base_dir = tmp_path / "files"
    base_dir.mkdir(exist_ok=True)
    file_path = base_dir / "sample.bin"
    data = b"0123456789"
    file_path.write_bytes(data)

    with pytest.raises(CollectionError):
        list(
            stream_binary_file(
                file_path,
                chunk_size=4,
                max_bytes=8,
            )
        )


@pytest.mark.asyncio
async def test_async_stream_text_file_matches_sync(tmp_path: Path) -> None:
    """Async streaming should mirror synchronous text content."""

    base_dir = tmp_path / "files"
    base_dir.mkdir(exist_ok=True)
    file_path = base_dir / "sample_async.txt"
    content = "Lorem ipsum dolor sit amet, consectetur adipiscing elit." * 5
    file_path.write_text(content, encoding="utf-8")

    collected: list[str] = []
    async for chunk in async_stream_text_file(
        file_path,
        chunk_size=40,
        max_bytes=None,
        encoding="utf-8",
        errors="strict",
    ):
        collected.append(chunk)

    assert "".join(collected) == content


@pytest.mark.asyncio
async def test_async_stream_binary_file_matches_sync(tmp_path: Path) -> None:
    """Async binary streaming should emit identical data."""

    base_dir = tmp_path / "files"
    base_dir.mkdir(exist_ok=True)
    file_path = base_dir / "sample_async.bin"
    data = b"abcdefghijklmnopqrstuvwxyz" * 4
    file_path.write_bytes(data)

    collected: list[bytes] = []
    async for chunk in async_stream_binary_file(
        file_path,
        chunk_size=10,
        max_bytes=None,
    ):
        collected.append(chunk)

    assert b"".join(collected) == data


@pytest.mark.asyncio
async def test_async_read_helpers_aggregate_streams(tmp_path: Path) -> None:
    """Async read helpers should aggregate streaming output faithfully."""

    base_dir = tmp_path / "files"
    base_dir.mkdir(exist_ok=True)
    text_file = base_dir / "full.txt"
    binary_file = base_dir / "full.bin"

    text_content = "Streaming makes large file handling efficient." * 6
    text_file.write_text(text_content, encoding="utf-8")

    binary_content = b"streaming-bytes" * 16
    binary_file.write_bytes(binary_content)

    aggregated_text = await async_read_text_file(
        text_file,
        chunk_size=64,
        max_bytes=None,
        encoding="utf-8",
        errors="strict",
    )
    aggregated_binary = await async_read_binary_file(
        binary_file,
        chunk_size=32,
        max_bytes=None,
    )

    assert aggregated_text == text_content
    assert aggregated_binary == binary_content
