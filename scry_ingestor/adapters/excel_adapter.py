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
        """Validate Excel content against configured schema expectations."""

        validation_config = self.config.get("validation") or {}

        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, Any] = {
            "row_count": len(raw_data),
            "column_count": len(raw_data.columns),
        }

        if raw_data.empty:
            errors.append("Excel sheet is empty")

        min_rows = validation_config.get("min_rows")
        if isinstance(min_rows, int) and metrics["row_count"] < min_rows:
            errors.append(
                f"Excel sheet has {metrics['row_count']} rows, minimum required is {min_rows}"
            )

        max_rows = validation_config.get("max_rows")
        if isinstance(max_rows, int) and metrics["row_count"] > max_rows:
            errors.append(
                f"Excel sheet has {metrics['row_count']} rows, maximum allowed is {max_rows}"
            )

        required_columns = validation_config.get("required_columns") or []
        missing_columns = [col for col in required_columns if col not in raw_data.columns]
        if missing_columns:
            metrics["missing_columns"] = missing_columns
            errors.append(
                "Excel sheet is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )
        else:
            metrics["missing_columns"] = []

        allow_empty_values = validation_config.get("allow_empty_values", True)
        if not allow_empty_values:
            has_empty_values = bool(raw_data.isna().any().any())
            if not has_empty_values:
                object_columns = raw_data.select_dtypes(include=["object", "string"])
                if not object_columns.empty:
                    normalized = object_columns.replace(r"^\s*$", pd.NA, regex=True)
                    has_empty_values = bool(normalized.isna().to_numpy().any())
            metrics["has_empty_values"] = has_empty_values
            if has_empty_values:
                errors.append(
                    "Excel sheet contains empty values but allow_empty_values is False"
                )
        else:
            metrics["has_empty_values"] = bool(raw_data.isna().any().any())

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    async def transform(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        return self._apply_transformations(raw_data)

    def _apply_transformations(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        """Apply optional transformations configured for the adapter."""

        transform_cfg = self.config.get("transformation")
        if not isinstance(transform_cfg, dict):
            transform_cfg = {}

        result = raw_data.copy()

        if transform_cfg.get("strip_whitespace", False):
            object_columns = result.select_dtypes(include=["object", "string"]).columns
            for column in object_columns:
                result[column] = result[column].apply(
                    lambda value: value.strip() if isinstance(value, str) else value
                )

        if transform_cfg.get("lowercase_columns", False):
            result.columns = [str(column).lower() for column in result.columns]

        if transform_cfg.get("drop_duplicates", False):
            result = result.drop_duplicates()

        return result

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
