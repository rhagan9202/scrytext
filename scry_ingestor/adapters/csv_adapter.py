"""Adapter for collecting and processing CSV data."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from ..exceptions import CollectionError
from ..schemas.payload import ValidationResult
from ..utils.file_readers import read_text_file, resolve_text_read_options
from .base import BaseAdapter


class CSVAdapter(BaseAdapter):
    """Adapter for CSV files using pandas."""

    async def collect(self) -> pd.DataFrame:
        source_type = self.config.get("source_type", "file")
        csv_options = self._resolve_csv_options()

        try:
            if source_type == "file":
                file_path = self.config.get("path")
                if not file_path:
                    raise CollectionError("CSV file path not provided in config")

                chunk_size, max_bytes, encoding, errors = resolve_text_read_options(
                    self.config.get("read_options")
                )
                text_data = await self._run_in_thread(
                    read_text_file,
                    file_path,
                    chunk_size=chunk_size,
                    max_bytes=max_bytes,
                    encoding=encoding,
                    errors=errors,
                )
                return await self._run_in_thread(
                    pd.read_csv,
                    io.StringIO(text_data),
                    **csv_options,
                )

            elif source_type == "string":
                data = self.config.get("data")
                if not data:
                    raise CollectionError("CSV string not provided in config")
                return await self._run_in_thread(
                    pd.read_csv,
                    io.StringIO(data),
                    **csv_options,
                )

            raise CollectionError(f"Unsupported source type: {source_type}")

        except CollectionError:
            raise
        except Exception as exc:
            raise CollectionError(f"Failed to collect CSV data: {exc}") from exc

    async def validate(self, raw_data: pd.DataFrame) -> ValidationResult:
        errors = []
        warnings = []
        metrics = {"row_count": len(raw_data), "column_count": len(raw_data.columns)}
        if raw_data.empty:
            errors.append("CSV file is empty")
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    async def transform(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        # Optionally clean or normalize data here
        return raw_data

    def _resolve_csv_options(self) -> dict[str, Any]:
        """Return a validated pandas option mapping for CSV parsing."""

        options = self.config.get("csv_options")
        if options is None:
            return {}
        if not isinstance(options, dict):
            raise CollectionError("'csv_options' must be a mapping of pandas options")

        normalized: dict[str, Any] = {}
        key_mapping = {
            "skip_rows": "skiprows",
        }

        for key, value in options.items():
            mapped_key = key_mapping.get(key, key)
            if not isinstance(mapped_key, str):
                raise CollectionError("CSV option keys must be strings")
            if mapped_key == "encoding":
                # Encoding is handled by chunked reader.
                continue
            if value is None:
                continue
            normalized[mapped_key] = value

        return normalized
