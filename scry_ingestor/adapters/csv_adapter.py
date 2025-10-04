"""Adapter for collecting and processing CSV data."""
import pandas as pd
from typing import Any

from .base import BaseAdapter
from ..exceptions import CollectionError, TransformationError, ValidationError
from ..schemas.payload import ValidationResult

class CSVAdapter(BaseAdapter):
    """Adapter for CSV files using pandas."""

    async def collect(self) -> pd.DataFrame:
        source_type = self.config.get("source_type", "file")
        try:
            if source_type == "file":
                file_path = self.config.get("path")
                if not file_path:
                    raise CollectionError("CSV file path not provided in config")
                return pd.read_csv(file_path)
            elif source_type == "string":
                import io
                data = self.config.get("data")
                if not data:
                    raise CollectionError("CSV string not provided in config")
                return pd.read_csv(io.StringIO(data))
            else:
                raise CollectionError(f"Unsupported source type: {source_type}")
        except Exception as e:
            raise CollectionError(f"Failed to collect CSV data: {e}")

    async def validate(self, raw_data: pd.DataFrame) -> ValidationResult:
        errors = []
        warnings = []
        metrics = {"row_count": len(raw_data), "column_count": len(raw_data.columns)}
        if raw_data.empty:
            errors.append("CSV file is empty")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics)

    async def transform(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        # Optionally clean or normalize data here
        return raw_data
