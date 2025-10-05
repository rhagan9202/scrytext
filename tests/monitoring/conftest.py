"""Shared fixtures for monitoring test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scry_ingestor.monitoring.tracing import clear_correlation_id


@pytest.fixture(autouse=True)
def reset_correlation_context() -> Iterator[None]:
    """Ensure correlation ID context starts clean for every test."""

    clear_correlation_id()
    yield
    clear_correlation_id()
