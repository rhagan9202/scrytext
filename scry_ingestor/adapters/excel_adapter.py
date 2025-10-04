"""Adapter for collecting and processing Excel data."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from ..exceptions import CollectionError
from ..schemas.payload import ValidationResult
from ..utils.file_readers import read_binary_file, resolve_binary_read_options
from .base import BaseAdapter


class ExcelAdapter(BaseAdapter):
    """Adapter for Excel files using pandas."""

    async def collect(self) -> pd.DataFrame:
        source_type = self.config.get("source_type", "file")
        sheet_name = self.config.get(
            "sheet_name",
            self.config.get("default_sheet", 0),
        )
        excel_options = self._resolve_excel_options()

        try:
            if source_type == "file":
                file_path = self.config.get("path")
                if not file_path:
                    raise CollectionError("Excel file path not provided in config")

                chunk_size, max_bytes = resolve_binary_read_options(
                    self.config.get("read_options")
                )
                data_bytes = await self._run_in_thread(
                    read_binary_file,
                    file_path,
                    chunk_size=chunk_size,
                    max_bytes=max_bytes,
                )
                buffer = io.BytesIO(data_bytes)
                return await self._run_in_thread(
                    pd.read_excel,
                    buffer,
                    sheet_name=sheet_name,
                    **excel_options,
                )

            elif source_type == "string":
                data = self.config.get("data")
                if not data:
                    raise CollectionError("Excel bytes not provided in config")
                buffer = io.BytesIO(data)
                return await self._run_in_thread(
                    pd.read_excel,
                    buffer,
                    sheet_name=sheet_name,
                    **excel_options,
                )

            else:
                raise CollectionError(f"Unsupported source type: {source_type}")
        except CollectionError:
            raise
        except Exception as exc:
            raise CollectionError(f"Failed to collect Excel data: {exc}") from exc

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

    def _resolve_excel_options(self) -> dict[str, Any]:
        """Return sanitized pandas options for Excel ingestion."""

        options = self.config.get("excel_options")
        if options is None:
            return {}
        if not isinstance(options, dict):
            raise CollectionError("'excel_options' must be a mapping of pandas options")

        normalized: dict[str, Any] = {}
        key_mapping = {
            "skip_rows": "skiprows",
            "use_columns": "usecols",
        }
        for key, value in options.items():
            mapped_key = key_mapping.get(key, key)
            if not isinstance(mapped_key, str):
                raise CollectionError("Excel option keys must be strings")
            if value is None:
                continue
            normalized[mapped_key] = value

        return normalized
