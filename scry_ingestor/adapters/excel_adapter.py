"""Adapter for collecting and processing Excel data."""

import pandas as pd

from .base import BaseAdapter
from ..exceptions import CollectionError
from ..schemas.payload import ValidationResult


class ExcelAdapter(BaseAdapter):
    """Adapter for Excel files using pandas."""

    async def collect(self) -> pd.DataFrame:
        source_type = self.config.get("source_type", "file")
        try:
            if source_type == "file":
                file_path = self.config.get("path")
                if not file_path:
                    raise CollectionError("Excel file path not provided in config")
                sheet_name = self.config.get("sheet_name", 0)
                return await self._run_in_thread(pd.read_excel, file_path, sheet_name=sheet_name)
            elif source_type == "string":
                data = self.config.get("data")
                if not data:
                    raise CollectionError("Excel bytes not provided in config")
                sheet_name = self.config.get("sheet_name", 0)
                import io

                buffer = io.BytesIO(data)
                return await self._run_in_thread(pd.read_excel, buffer, sheet_name=sheet_name)
            else:
                raise CollectionError(f"Unsupported source type: {source_type}")
        except Exception as e:
            raise CollectionError(f"Failed to collect Excel data: {e}")

    async def validate(self, raw_data: pd.DataFrame) -> ValidationResult:
        errors = []
        warnings = []
        metrics = {"row_count": len(raw_data), "column_count": len(raw_data.columns)}
        if raw_data.empty:
            errors.append("Excel sheet is empty")
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    async def transform(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        # Optionally clean or normalize data here
        return raw_data
