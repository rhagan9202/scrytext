"""Adapter registry for managing available data source adapters."""

from typing import Dict, Type
from .base import BaseAdapter

# Adapter registry - register new adapters here
_ADAPTER_REGISTRY: Dict[str, Type[BaseAdapter]] = {}


def register_adapter(name: str, adapter_class: Type[BaseAdapter]) -> None:
    """
    Register a new adapter class.

    Args:
        name: Unique identifier for the adapter
        adapter_class: Adapter class to register
    """
    _ADAPTER_REGISTRY[name] = adapter_class


def get_adapter(name: str) -> Type[BaseAdapter]:
    """
    Get an adapter class by name.

    Args:
        name: Adapter identifier

    Returns:
        Adapter class

    Raises:
        KeyError: If adapter is not registered
    """
    if name not in _ADAPTER_REGISTRY:
        raise KeyError(f"Adapter '{name}' not found. Available: {list(_ADAPTER_REGISTRY.keys())}")
    return _ADAPTER_REGISTRY[name]


def list_adapters() -> list[str]:
    """Return list of registered adapter names."""
    return list(_ADAPTER_REGISTRY.keys())


# Import and register adapters here as they're created
from .csv_adapter import CSVAdapter
from .excel_adapter import ExcelAdapter
from .json_adapter import JSONAdapter
from .pdf_adapter import PDFAdapter
from .word_adapter import WordAdapter

register_adapter("json", JSONAdapter)
register_adapter("csv", CSVAdapter)
register_adapter("excel", ExcelAdapter)
register_adapter("word", WordAdapter)
register_adapter("pdf", PDFAdapter)
