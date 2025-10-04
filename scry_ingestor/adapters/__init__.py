"""Adapter registry for managing available data source adapters."""

from ..exceptions import AdapterNotFoundError
from .base import BaseAdapter
from .csv_adapter import CSVAdapter
from .excel_adapter import ExcelAdapter
from .json_adapter import JSONAdapter
from .pdf_adapter import PDFAdapter
from .word_adapter import WordAdapter

# Adapter registry - register new adapters here
_ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {}


def register_adapter(name: str, adapter_class: type[BaseAdapter]) -> None:
    """
    Register a new adapter class.

    Args:
        name: Unique identifier for the adapter
        adapter_class: Adapter class to register
    """
    _ADAPTER_REGISTRY[name] = adapter_class


def get_adapter(name: str) -> type[BaseAdapter]:
    """
    Get an adapter class by name.

    Args:
        name: Adapter identifier

    Returns:
        Adapter class

    Raises:
        AdapterNotFoundError: If adapter is not registered
    """
    if name not in _ADAPTER_REGISTRY:
        available = sorted(_ADAPTER_REGISTRY.keys())
        available_display = ", ".join(available) if available else "none"
        raise AdapterNotFoundError(
            f"Adapter '{name}' is not registered. Available adapters: {available_display}."
        )
    return _ADAPTER_REGISTRY[name]


def list_adapters() -> list[str]:
    """Return list of registered adapter names."""
    return list(_ADAPTER_REGISTRY.keys())


register_adapter("json", JSONAdapter)
register_adapter("csv", CSVAdapter)
register_adapter("excel", ExcelAdapter)
register_adapter("word", WordAdapter)
register_adapter("pdf", PDFAdapter)
