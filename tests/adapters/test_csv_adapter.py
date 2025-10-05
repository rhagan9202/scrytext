"""Tests for CSVAdapter using live test data."""
import pandas as pd
import pytest

from scry_ingestor.adapters.csv_adapter import CSVAdapter
from scry_ingestor.exceptions import CollectionError


class TestCSVAdapter:
    """Test suite for CSVAdapter with live fixtures."""

    @pytest.mark.asyncio
    async def test_collect_from_file(self, sample_csv_config):
        """Test collecting CSV from a file using live test data."""
        adapter = CSVAdapter(sample_csv_config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) == 5  # 5 employees in sample
        assert "name" in raw_data.columns
        assert "email" in raw_data.columns
        assert raw_data.iloc[0]["name"] == "Alice Johnson"

    @pytest.mark.asyncio
    async def test_collect_from_string(self, sample_csv_string_config):
        """Test collecting CSV from a string."""
        adapter = CSVAdapter(sample_csv_string_config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) == 3
        assert list(raw_data.columns) == ["id", "value", "description"]

    @pytest.mark.asyncio
    async def test_validate_valid_csv(self, sample_csv_config):
        """Test validation of valid CSV data."""
        adapter = CSVAdapter(sample_csv_config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is True
        assert len(validation.errors) == 0
        assert validation.metrics["row_count"] == 5
        assert validation.metrics["column_count"] == 6

    @pytest.mark.asyncio
    async def test_validate_missing_required_columns(self, sample_csv_config):
        """CSV validation should fail when required columns are absent."""

        config = {
            **sample_csv_config,
            "validation": {
                "required_columns": ["name", "email", "employee_id"],
            },
        }

        adapter = CSVAdapter(config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is False
        assert any("missing required columns" in error for error in validation.errors)
        assert "employee_id" in validation.metrics["missing_columns"]

    @pytest.mark.asyncio
    async def test_validate_empty_csv(self):
        """Test validation of empty CSV."""
        adapter = CSVAdapter({"source_id": "test", "source_type": "string", "data": "col1\n"})
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is False
        assert "empty" in validation.errors[0].lower()

    @pytest.mark.asyncio
    async def test_transform_csv(self, sample_csv_config):
        """Test transformation of CSV DataFrame."""
        adapter = CSVAdapter(sample_csv_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert isinstance(transformed, pd.DataFrame)
        assert len(transformed) == 5
        # Verify data integrity after transformation
        assert transformed.iloc[0]["email"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_csv_config):
        """Test the complete ingestion pipeline with live CSV data."""
        adapter = CSVAdapter(sample_csv_config)
        payload = await adapter.process()

        # Check data
        assert isinstance(payload.data, pd.DataFrame)
        assert len(payload.data) == 5
        assert "department" in payload.data.columns

        # Check metadata
        assert payload.metadata.source_id == "test-csv-source"
        assert payload.metadata.adapter_type == "CSVAdapter"
        assert payload.metadata.processing_mode == "local"
        assert payload.metadata.processing_duration_ms >= 0

        # Check validation
        assert payload.validation.is_valid is True
        assert payload.validation.metrics["row_count"] == 5

    @pytest.mark.asyncio
    async def test_missing_file_raises_error(self):
        """Test that missing file raises CollectionError."""
        config = {
            "source_id": "missing-file",
            "source_type": "file",
            "path": "tests/fixtures/nonexistent.csv",
        }
        adapter = CSVAdapter(config)

        with pytest.raises(CollectionError):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_missing_config_raises_error(self):
        """Test that missing required config raises CollectionError."""
        config = {"source_id": "test", "source_type": "file"}
        adapter = CSVAdapter(config)

        with pytest.raises(CollectionError, match="path not provided"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_csv_with_numeric_data(self, sample_csv_config):
        """Test CSV with numeric columns."""
        adapter = CSVAdapter(sample_csv_config)
        payload = await adapter.process()

        # Check that numeric columns are preserved
        assert payload.data["age"].dtype in ["int64", "float64"]
        assert payload.data["salary"].dtype in ["int64", "float64"]
        assert payload.data["age"].mean() > 0

    @pytest.mark.asyncio
    async def test_collect_with_chunked_read_options(self, sample_csv_config):
        """Ensure chunked read options still load full CSV content."""

        config = {**sample_csv_config}
        config["read_options"] = {
            "chunk_size": 16,
            "encoding": "utf-8",
        }

        adapter = CSVAdapter(config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) == 5

    @pytest.mark.asyncio
    async def test_collect_respects_max_bytes_limit(self, sample_csv_config):
        """Chunked reader should guard against oversized CSV files."""

        config = {**sample_csv_config}
        config["read_options"] = {"max_bytes": 32}

        adapter = CSVAdapter(config)

        with pytest.raises(CollectionError, match="max_bytes"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_collect_with_invalid_read_options_logs_warning(
        self, sample_csv_config, caplog
    ):
        """Ensure non-mapping read_options emit a warning and fall back."""

        config = {**sample_csv_config}
        config["read_options"] = ["not", "a", "mapping"]

        adapter = CSVAdapter(config)
        with caplog.at_level("WARNING", logger="scry_ingestor.utils.file_readers"):
            raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert any("not a mapping" in message for message in caplog.messages)

    @pytest.mark.asyncio
    async def test_collect_with_invalid_read_option_values_warns(
        self, sample_csv_config, caplog
    ):
        """Invalid option values should trigger warnings and default handling."""

        config = {**sample_csv_config}
        config["read_options"] = {
            "chunk_size": -128,
            "encoding": 123,
            "errors": 42,
            "max_bytes": "ten",
            "unexpected": True,
        }

        adapter = CSVAdapter(config)
        with caplog.at_level("WARNING", logger="scry_ingestor.utils.file_readers"):
            raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        messages = " ".join(caplog.messages)
        assert "must be greater than zero" in messages
        assert "Invalid encoding value" in messages
        assert "Invalid errors mode" in messages
        assert "Invalid max_bytes value" in messages
        assert "Ignoring unsupported" in messages
