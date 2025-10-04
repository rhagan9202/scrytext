"""Tests for adapter registry behavior."""

import pytest

from scry_ingestor.adapters import get_adapter
from scry_ingestor.adapters.csv_adapter import CSVAdapter
from scry_ingestor.exceptions import AdapterNotFoundError


def test_get_adapter_returns_registered_class() -> None:
    """Ensure a registered adapter can be retrieved successfully."""
    adapter_class = get_adapter("csv")
    assert adapter_class is CSVAdapter


def test_get_adapter_missing_adapter_raises_custom_error() -> None:
    """An unknown adapter name should raise AdapterNotFoundError."""
    with pytest.raises(AdapterNotFoundError) as exc:
        get_adapter("nonexistent")

    message = str(exc.value)
    assert "nonexistent" in message
    assert "Available adapters" in message
