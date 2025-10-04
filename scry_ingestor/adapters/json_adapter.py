"""Example JSON adapter demonstrating the adapter pattern."""

import json
from typing import Any

from .base import BaseAdapter
from ..exceptions import CollectionError, TransformationError
from ..schemas.payload import ValidationResult


class JSONAdapter(BaseAdapter):
    """
    Adapter for collecting and processing JSON data from various sources.

    Supports:
    - Local file paths
    - Raw JSON strings
    - URLs (when cloud processing is enabled)
    """

    async def collect(self) -> str:
        """
        Collect raw JSON data from the configured source.

        Returns:
            Raw JSON string

        Raises:
            CollectionError: If data collection fails
        """
        source_type = self.config.get("source_type", "file")

        try:
            if source_type == "file":
                file_path = self.config.get("path")
                if not file_path:
                    raise CollectionError("File path not provided in config")
                return await self._run_in_thread(self._read_file, file_path)

            elif source_type == "string":
                raw_data = self.config.get("data")
                if not raw_data:
                    raise CollectionError("JSON string not provided in config")
                return raw_data

            else:
                raise CollectionError(f"Unsupported source type: {source_type}")

        except OSError as e:
            raise CollectionError(f"Failed to collect JSON data: {e}")

    async def validate(self, raw_data: str) -> ValidationResult:
        """
        Validate the JSON data structure and content.

        Args:
            raw_data: Raw JSON string

        Returns:
            ValidationResult with quality metrics
        """
        errors = []
        warnings = []
        metrics = {}

        # Check if data is valid JSON
        try:
            parsed = json.loads(raw_data)
            metrics["valid_json"] = True
            metrics["data_size_bytes"] = len(raw_data)

            # Additional validation based on expected schema
            expected_schema = self.config.get("expected_schema")
            if expected_schema:
                missing_keys = set(expected_schema) - set(parsed.keys())
                if missing_keys:
                    warnings.append(f"Missing expected keys: {missing_keys}")

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON: {e}")
            metrics["valid_json"] = False

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid, errors=errors, warnings=warnings, metrics=metrics
        )

    async def transform(self, raw_data: str) -> dict[str, Any]:
        """
        Transform raw JSON string into Python dictionary.

        Args:
            raw_data: Raw JSON string

        Returns:
            Parsed JSON as dictionary

        Raises:
            TransformationError: If JSON parsing fails
        """
        try:
            parsed = json.loads(raw_data)

            # Apply any transformations specified in config
            if self.config.get("flatten", False):
                # Example: flatten nested structures (simplified)
                parsed = self._flatten_dict(parsed)

            return parsed

        except json.JSONDecodeError as e:
            raise TransformationError(f"Failed to parse JSON: {e}")

    def _flatten_dict(self, d: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
        """Helper to flatten nested dictionaries."""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)

    @staticmethod
    def _read_file(file_path: str) -> str:
        """Synchronous helper to read file contents."""
        with open(file_path) as file_handle:
            return file_handle.read()
