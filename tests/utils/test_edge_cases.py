"""Tests for utility functions to improve edge case coverage."""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scry_ingestor.exceptions import ConfigurationError
from scry_ingestor.utils.config import (
    apply_env_overrides,
    load_yaml_config,
    validate_config,
)
from scry_ingestor.utils.file_readers import (
    read_binary_file,
    read_text_file,
    resolve_binary_read_options,
    resolve_text_read_options,
)
from scry_ingestor.utils.logging import StructuredLoggerAdapter, setup_logger


class TestConfigUtils:
    """Test suite for configuration utilities."""

    def test_load_yaml_config_file_not_found(self):
        """Test loading non-existent YAML file raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            load_yaml_config("/nonexistent/file.yaml")

    def test_load_yaml_config_invalid_yaml(self):
        """Test loading invalid YAML raises ConfigurationError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [\n")
            f.flush()
            tmp_path = f.name

        try:
            with pytest.raises(ConfigurationError, match="Invalid YAML"):
                load_yaml_config(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_load_yaml_config_empty_file(self):
        """Test loading empty YAML file returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            tmp_path = f.name

        try:
            result = load_yaml_config(tmp_path)
            assert result == {}
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_load_yaml_config_valid_file(self):
        """Test loading valid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\nnested:\n  inner: data\n")
            f.flush()
            tmp_path = f.name

        try:
            result = load_yaml_config(tmp_path)
            assert result == {"key": "value", "nested": {"inner": "data"}}
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_apply_env_overrides_no_prefix_match(self, monkeypatch):
        """Test env overrides with no matching prefix."""
        # Clear any existing SCRY_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("SCRY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("OTHER_VAR", "value")
        config = {"existing": "value"}
        result = apply_env_overrides(config, prefix="SCRY_")
        assert result == {"existing": "value"}

    def test_apply_env_overrides_simple_key(self, monkeypatch):
        """Test env overrides with simple key."""
        # Clear any existing SCRY_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("SCRY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("SCRY_DEBUG", "true")
        config = {}
        result = apply_env_overrides(config, prefix="SCRY_")
        assert result == {"debug": "true"}

    def test_apply_env_overrides_nested_key(self, monkeypatch):
        """Test env overrides with nested key using __."""
        # Clear any existing SCRY_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("SCRY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("SCRY_AWS__REGION", "us-west-2")
        monkeypatch.setenv("SCRY_DB__HOST", "localhost")
        config = {}
        result = apply_env_overrides(config, prefix="SCRY_")
        assert result == {
            "aws": {"region": "us-west-2"},
            "db": {"host": "localhost"},
        }

    def test_apply_env_overrides_deep_nested(self, monkeypatch):
        """Test env overrides with deeply nested keys."""
        # Clear any existing SCRY_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("SCRY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("SCRY_A__B__C__D", "deep_value")
        config = {}
        result = apply_env_overrides(config, prefix="SCRY_")
        assert result == {"a": {"b": {"c": {"d": "deep_value"}}}}

    def test_apply_env_overrides_overwrites_existing(self, monkeypatch):
        """Test env overrides overwrites existing values."""
        # Clear any existing SCRY_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("SCRY_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("SCRY_EXISTING", "new_value")
        config = {"existing": "old_value"}
        result = apply_env_overrides(config, prefix="SCRY_")
        assert result == {"existing": "new_value"}

    def test_validate_config_success(self):
        """Test successful config validation."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            count: int = 0

        config = {"name": "test", "count": 5}
        result = validate_config(config, TestModel)
        assert result.model_dump()["name"] == "test"
        assert result.model_dump()["count"] == 5

    def test_validate_config_failure(self):
        """Test config validation failure."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            count: int

        config = {"name": "test", "count": "invalid"}
        with pytest.raises(ConfigurationError, match="Configuration validation failed"):
            validate_config(config, TestModel)


class TestFileReaders:
    """Test suite for file reader utilities."""

    def test_resolve_text_read_options_defaults(self):
        """Test text read options with defaults."""
        chunk_size, max_bytes, encoding, errors = resolve_text_read_options({})
        assert chunk_size == 1048576  # 1MB default
        assert max_bytes is None
        assert encoding == "utf-8"
        assert errors == "strict"

    def test_resolve_text_read_options_custom(self):
        """Test text read options with custom values."""
        custom = {
            "chunk_size": 1024,
            "max_bytes": 5000,
            "encoding": "latin-1",
            "errors": "ignore",
        }
        chunk_size, max_bytes, encoding, errors = resolve_text_read_options(custom)
        assert chunk_size == 1024
        assert max_bytes == 5000
        assert encoding == "latin-1"
        assert errors == "ignore"

    def test_resolve_text_read_options_invalid_chunk_size(self, caplog):
        """Test text read options with invalid chunk size logs warning."""
        with caplog.at_level(logging.WARNING):
            chunk_size, max_bytes, encoding, errors = resolve_text_read_options({"chunk_size": 0})

        assert "chunk_size must be greater than zero" in caplog.text
        assert chunk_size == 1048576  # Falls back to default

    def test_resolve_text_read_options_invalid_max_bytes(self, caplog):
        """Test text read options with invalid max_bytes logs warning."""
        with caplog.at_level(logging.WARNING):
            chunk_size, max_bytes, encoding, errors = resolve_text_read_options(
                {"max_bytes": "invalid"}
            )

        assert "Invalid max_bytes value" in caplog.text
        assert max_bytes is None  # Falls back to default

    def test_resolve_text_read_options_invalid_encoding(self, caplog):
        """Test text read options with invalid encoding logs warning."""
        with caplog.at_level(logging.WARNING):
            chunk_size, max_bytes, encoding, errors = resolve_text_read_options({"encoding": 123})

        assert "Invalid encoding value" in caplog.text
        assert encoding == "utf-8"  # Falls back to default

    def test_resolve_binary_read_options_defaults(self):
        """Test binary read options with defaults."""
        chunk_size, max_bytes = resolve_binary_read_options({})
        assert chunk_size == 1048576  # 1MB default
        assert max_bytes is None

    def test_resolve_binary_read_options_custom(self):
        """Test binary read options with custom values."""
        custom = {"chunk_size": 2048, "max_bytes": 10000}
        chunk_size, max_bytes = resolve_binary_read_options(custom)
        assert chunk_size == 2048
        assert max_bytes == 10000

    def test_resolve_binary_read_options_invalid_values(self, caplog):
        """Test binary read options with invalid values logs warnings."""
        with caplog.at_level(logging.WARNING):
            chunk_size, max_bytes = resolve_binary_read_options(
                {
                    "chunk_size": -1,
                    "max_bytes": "not_a_number",
                    "unknown_option": "value",
                }
            )

        messages = caplog.text
        assert "chunk_size must be greater than zero" in messages
        assert "Invalid max_bytes value" in messages
        assert "Ignoring unsupported" in messages

        # Should fall back to defaults for invalid values
        assert chunk_size == 1048576
        assert max_bytes is None

    def test_resolve_text_read_options_max_bytes_smaller_than_chunk(self, caplog):
        """Test handling when max_bytes is smaller than chunk_size."""
        with caplog.at_level(logging.WARNING):
            chunk_size, max_bytes, encoding, errors = resolve_text_read_options(
                {
                    "chunk_size": 2000,
                    "max_bytes": 1000,
                }
            )

        assert "max_bytes (1000) is smaller than chunk_size" in caplog.text
        assert chunk_size == 1000  # Should be reduced to match max_bytes
        assert max_bytes == 1000

    def test_read_text_file_success(self):
        """Test successful text file reading."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write("Hello, World!\nLine 2\n")
            f.flush()
            tmp_path = f.name

        try:
            content = read_text_file(
                tmp_path, chunk_size=1024, max_bytes=None, encoding="utf-8", errors="strict"
            )
            assert content == "Hello, World!\nLine 2\n"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_read_text_file_with_max_bytes_limit(self):
        """Test text file reading with max_bytes limit."""
        test_content = "A" * 1000  # 1000 characters
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write(test_content)
            f.flush()
            tmp_path = f.name

        try:
            # Should raise CollectionError due to max_bytes limit
            with pytest.raises(Exception):  # CollectionError
                read_text_file(
                    tmp_path, chunk_size=100, max_bytes=500, encoding="utf-8", errors="strict"
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_read_text_file_not_found(self):
        """Test reading non-existent text file raises exception."""
        with pytest.raises(Exception):  # Should raise CollectionError
            read_text_file(
                "/nonexistent/file.txt",
                chunk_size=1024,
                max_bytes=None,
                encoding="utf-8",
                errors="strict",
            )

    def test_read_binary_file_success(self):
        """Test successful binary file reading."""
        test_data = b"Binary data \x00\x01\x02"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(test_data)
            f.flush()
            tmp_path = f.name

        try:
            content = read_binary_file(tmp_path, chunk_size=1024, max_bytes=None)
            assert content == test_data
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_read_binary_file_with_max_bytes_limit(self):
        """Test binary file reading with max_bytes limit."""
        test_data = b"A" * 1000
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(test_data)
            f.flush()
            tmp_path = f.name

        try:
            # Should raise CollectionError due to max_bytes limit
            with pytest.raises(Exception):  # CollectionError
                read_binary_file(tmp_path, chunk_size=100, max_bytes=500)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestLoggingUtils:
    """Test suite for logging utilities."""

    @patch("scry_ingestor.utils.logging.logging.getLogger")
    def test_setup_logger_basic(self, mock_get_logger):
        """Test basic logger setup."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        logger = setup_logger("test.module")

        # Should return a StructuredLoggerAdapter wrapping the logger
        assert isinstance(logger, StructuredLoggerAdapter)
        assert logger.logger == mock_logger
        mock_get_logger.assert_called_once_with("test.module")

    @patch("scry_ingestor.utils.logging.logging.getLogger")
    def test_setup_logger_with_context(self, mock_get_logger):
        """Test logger setup with context."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        context = {"adapter_type": "TestAdapter", "source_id": "test-123"}
        logger = setup_logger("test.module", context=context)

        # Should return a StructuredLoggerAdapter with custom context
        assert isinstance(logger, StructuredLoggerAdapter)
        assert logger.logger == mock_logger
        # Context should be stored for later use in log messages

    def test_logger_context_integration(self):
        """Test that logger context is properly integrated."""
        # This is more of an integration test with real logging
        logger = setup_logger("test.integration", context={"test": "value"})

        # Should not raise an exception
        logger.info("Test message")
        assert True  # If we get here, no exception was raised


class TestEdgeCases:
    """Test edge cases across utility functions."""

    def test_file_operations_with_empty_files(self):
        """Test file operations with empty files."""
        # Empty text file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.flush()
            tmp_path = f.name

        try:
            content = read_text_file(
                tmp_path, chunk_size=1024, max_bytes=None, encoding="utf-8", errors="strict"
            )
            assert content == ""
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # Empty binary file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.flush()
            tmp_path = f.name

        try:
            content = read_binary_file(tmp_path, chunk_size=1024, max_bytes=None)
            assert content == b""
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_config_edge_cases(self, monkeypatch):
        """Test configuration edge cases."""
        # Clear any existing SCRY_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("SCRY_"):
                monkeypatch.delenv(key, raising=False)

        # Empty config
        result = apply_env_overrides({})
        assert result == {}

        # None values in YAML
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: null\nother: ~\n")
            f.flush()
            tmp_path = f.name

        try:
            result = load_yaml_config(tmp_path)
            assert result == {"key": None, "other": None}
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_file_readers_with_unsupported_options(self, caplog):
        """Test file readers warn about unsupported options."""
        with caplog.at_level(logging.WARNING):
            chunk_size, max_bytes = resolve_binary_read_options(
                {
                    "chunk_size": 1024,
                    "max_bytes": 5000,
                    "unsupported_option": "value",
                    "another_bad_option": 123,
                }
            )

        messages = caplog.text
        assert "Ignoring unsupported" in messages
        assert "unsupported_option" in messages
        assert chunk_size == 1024
        assert max_bytes == 5000
