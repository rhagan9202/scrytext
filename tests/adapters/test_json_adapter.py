"""Tests for JSONAdapter using live test data."""
import json
import pytest

from scry_ingestor.adapters.json_adapter import JSONAdapter
from scry_ingestor.exceptions import CollectionError


class TestJSONAdapter:
    """Test suite for JSONAdapter with live fixtures."""

    @pytest.mark.asyncio
    async def test_collect_from_file(self, sample_json_config):
        """Test collecting JSON from a file using live test data."""
        adapter = JSONAdapter(sample_json_config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, str)
        assert len(raw_data) > 0
        # Verify it's valid JSON
        parsed = json.loads(raw_data)
        assert "name" in parsed
        assert parsed["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_collect_from_string(self, sample_json_string_config):
        """Test collecting JSON from a string."""
        adapter = JSONAdapter(sample_json_string_config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, str)
        parsed = json.loads(raw_data)
        assert parsed["name"] == "test"
        assert parsed["value"] == 42

    @pytest.mark.asyncio
    async def test_validate_valid_json(self, sample_json_string_config):
        """Test validation of valid JSON data."""
        adapter = JSONAdapter(sample_json_string_config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is True
        assert len(validation.errors) == 0
        assert validation.metrics["valid_json"] is True
        assert validation.metrics["data_size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_validate_invalid_json(self, sample_json_config):
        """Test validation of invalid JSON."""
        adapter = JSONAdapter(sample_json_config)
        invalid_json = '{"name": "test", invalid}'
        validation = await adapter.validate(invalid_json)

        assert validation.is_valid is False
        assert len(validation.errors) > 0
        assert "Invalid JSON" in validation.errors[0]
        assert validation.metrics["valid_json"] is False

    @pytest.mark.asyncio
    async def test_transform_json(self, sample_json_string_config):
        """Test transformation of JSON string to dictionary."""
        adapter = JSONAdapter(sample_json_string_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert isinstance(transformed, dict)
        assert transformed["name"] == "test"
        assert transformed["value"] == 42
        assert transformed["nested"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_transform_with_flattening(self, sample_json_string_config):
        """Test transformation with flattening enabled."""
        sample_json_string_config["flatten"] = True
        adapter = JSONAdapter(sample_json_string_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert isinstance(transformed, dict)
        assert "nested.key" in transformed
        assert transformed["nested.key"] == "value"

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_json_config):
        """Test the complete ingestion pipeline with live data."""
        adapter = JSONAdapter(sample_json_config)
        payload = await adapter.process()

        # Check data
        assert isinstance(payload.data, dict)
        assert payload.data["name"] == "Test User"
        assert payload.data["email"] == "test@example.com"

        # Check metadata (access as attributes, not dict)
        assert payload.metadata.source_id == "test-json-source"
        assert payload.metadata.adapter_type == "JSONAdapter"
        assert payload.metadata.processing_mode == "local"
        assert payload.metadata.processing_duration_ms >= 0

        # Check validation
        assert payload.validation.is_valid is True
        assert len(payload.validation.errors) == 0

    @pytest.mark.asyncio
    async def test_missing_file_raises_error(self):
        """Test that missing file raises CollectionError."""
        config = {
            "source_id": "missing-file",
            "source_type": "file",
            "path": "tests/fixtures/nonexistent.json",
        }
        adapter = JSONAdapter(config)

        with pytest.raises(CollectionError):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_missing_config_raises_error(self):
        """Test that missing required config raises CollectionError."""
        config = {"source_id": "test", "source_type": "file"}
        adapter = JSONAdapter(config)

        with pytest.raises(CollectionError, match="File path not provided"):
            await adapter.collect()
