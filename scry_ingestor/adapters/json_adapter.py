"""Example JSON adapter demonstrating the adapter pattern."""

import json
from typing import Any

from ..exceptions import CollectionError, TransformationError
from ..schemas.payload import ValidationResult
from ..utils.file_readers import read_text_file, resolve_text_read_options
from .base import BaseAdapter


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
                chunk_size, max_bytes, encoding, errors = resolve_text_read_options(
                    self.config.get("read_options")
                )
                return await self._run_in_thread(
                    read_text_file,
                    file_path,
                    chunk_size=chunk_size,
                    max_bytes=max_bytes,
                    encoding=encoding,
                    errors=errors,
                )

            elif source_type == "string":
                raw_data = self.config.get("data")
                if not raw_data:
                    raise CollectionError("JSON string not provided in config")
                return str(raw_data)

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
        metrics: dict[str, Any] = {}

        # Check if data is valid JSON
        try:
            parsed = self._load_json(raw_data)
            metrics["valid_json"] = True
            size_bytes = len(raw_data.encode("utf-8"))
            metrics["data_size_bytes"] = size_bytes

            validation_cfg = self._resolve_validation_config()
            max_size_bytes = validation_cfg.get("max_size_bytes")
            if isinstance(max_size_bytes, int) and max_size_bytes > 0:
                if size_bytes > max_size_bytes:
                    errors.append(
                        f"JSON payload is {size_bytes} bytes, exceeds limit {max_size_bytes}"
                    )

            required_fields = validation_cfg.get("required_fields")
            if required_fields is not None:
                if isinstance(parsed, dict):
                    if isinstance(required_fields, list | tuple | set):
                        missing_required = set(required_fields) - set(parsed.keys())
                        if missing_required:
                            errors.append(
                                f"Missing required fields: {sorted(missing_required)}"
                            )
                    else:
                        warnings.append("required_fields must be a sequence of keys")
                else:
                    warnings.append("required_fields ignored for non-object JSON payloads")

            allow_null_values = validation_cfg.get("allow_null_values", True)
            if not allow_null_values:
                if isinstance(parsed, dict):
                    null_keys = [key for key, value in parsed.items() if value is None]
                    if null_keys:
                        errors.append(
                            "Null values not permitted for keys: "
                            + ", ".join(sorted(null_keys))
                        )
                elif isinstance(parsed, list):
                    if any(item is None for item in parsed):
                        errors.append("Null values not permitted in JSON list payload")

            # Additional validation based on expected schema
            expected_schema = self.config.get("expected_schema")
            if expected_schema:
                if isinstance(parsed, dict):
                    if isinstance(expected_schema, list | tuple | set):
                        missing_keys = set(expected_schema) - set(parsed.keys())
                        if missing_keys:
                            warnings.append(f"Missing expected keys: {missing_keys}")
                    else:
                        warnings.append(
                            "expected_schema must be a sequence of keys for JSON objects"
                        )
                else:
                    warnings.append("expected_schema ignored for non-object JSON payloads")

            flatten_enabled, _ = self._resolve_flatten_config()
            if flatten_enabled and not isinstance(parsed, dict):
                warnings.append("flatten ignored because JSON payload is not an object")

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON: {e}")
            metrics["valid_json"] = False
        except ValueError as e:
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
            parsed = self._load_json(raw_data)

            # Apply any transformations specified in config
            flatten_enabled, max_depth = self._resolve_flatten_config()
            if flatten_enabled:
                # Example: flatten nested structures (simplified)
                if isinstance(parsed, dict):
                    parsed = self._flatten_dict(parsed, max_depth=max_depth)

            return dict(parsed) if isinstance(parsed, dict) else parsed

        except json.JSONDecodeError as e:
            raise TransformationError(f"Failed to parse JSON: {e}")
        except ValueError as e:
            raise TransformationError(f"Failed to parse JSON: {e}")

    def _resolve_json_options(self) -> dict[str, Any]:
        """Return JSON parsing options from config."""

        options = self.config.get("json_options")
        if isinstance(options, dict):
            return options
        return {}

    def _resolve_validation_config(self) -> dict[str, Any]:
        """Return validation config from config."""

        validation = self.config.get("validation")
        if isinstance(validation, dict):
            return validation
        return {}

    def _resolve_flatten_config(self) -> tuple[bool, int | None]:
        """Return flatten settings and max depth."""

        json_options = self._resolve_json_options()
        transform_cfg = self.config.get("transformation")
        if not isinstance(transform_cfg, dict):
            transform_cfg = {}

        flatten_setting = self.config.get("flatten")
        if flatten_setting is None:
            flatten_setting = json_options.get("flatten")
        if flatten_setting is None:
            flatten_setting = transform_cfg.get("flatten_nested")

        max_depth = transform_cfg.get("max_depth")
        if isinstance(max_depth, bool):
            max_depth = None
        if max_depth is not None:
            try:
                max_depth = int(max_depth)
            except (TypeError, ValueError):
                max_depth = None
        if isinstance(max_depth, int) and max_depth < 0:
            max_depth = None

        return bool(flatten_setting), max_depth

    def _load_json(self, raw_data: str) -> Any:
        """Parse JSON with strictness based on config."""

        options = self._resolve_json_options()
        strict_value = options.get("strict")
        strict = True if strict_value is None else bool(strict_value)

        if strict:
            def _reject_constants(value: str) -> Any:
                raise ValueError(f"Invalid constant in JSON: {value}")

            return json.loads(raw_data, parse_constant=_reject_constants)

        return json.loads(raw_data)

    def _flatten_dict(
        self,
        d: dict[str, Any],
        parent_key: str = "",
        max_depth: int | None = None,
        current_depth: int = 0,
    ) -> dict[str, Any]:
        """Helper to flatten nested dictionaries."""
        items: list[tuple[str, Any]] = []
        for key, value in d.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                if max_depth is not None and current_depth >= max_depth:
                    items.append((new_key, value))
                else:
                    items.extend(
                        self._flatten_dict(
                            value,
                            new_key,
                            max_depth=max_depth,
                            current_depth=current_depth + 1,
                        ).items()
                    )
            else:
                items.append((new_key, value))
        return dict(items)
