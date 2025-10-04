"""Tests for ExcelAdapter using live test data."""
import pandas as pd
import pytest

from scry_ingestor.adapters.excel_adapter import ExcelAdapter
from scry_ingestor.exceptions import CollectionError


class TestExcelAdapter:
    """Test suite for ExcelAdapter with live fixtures."""

    @pytest.mark.asyncio
    async def test_collect_from_file(self, sample_excel_config):
        """Test collecting Excel from a file using live test data."""
        adapter = ExcelAdapter(sample_excel_config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) == 5  # 5 products in sample
        assert "product" in raw_data.columns
        assert "price" in raw_data.columns
        assert raw_data.iloc[0]["product"] == "Laptop"

    @pytest.mark.asyncio
    async def test_collect_with_sheet_name(self, sample_excel_config):
        """Test collecting from specific sheet."""
        adapter = ExcelAdapter(sample_excel_config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) > 0
        # Verify it read from the Products sheet
        assert "product" in raw_data.columns

    @pytest.mark.asyncio
    async def test_validate_valid_excel(self, sample_excel_config):
        """Test validation of valid Excel data."""
        adapter = ExcelAdapter(sample_excel_config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is True
        assert len(validation.errors) == 0
        assert validation.metrics["row_count"] == 5
        assert validation.metrics["column_count"] == 5

    @pytest.mark.asyncio
    async def test_validate_empty_excel(self):
        """Test validation of empty Excel sheet."""
        # Just test the validation logic directly with an empty DataFrame
        adapter = ExcelAdapter({"source_id": "test", "source_type": "file", "path": "dummy.xlsx"})
        validation = await adapter.validate(pd.DataFrame())

        assert validation.is_valid is False
        assert "empty" in validation.errors[0].lower()

    @pytest.mark.asyncio
    async def test_transform_excel(self, sample_excel_config):
        """Test transformation of Excel DataFrame."""
        adapter = ExcelAdapter(sample_excel_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert isinstance(transformed, pd.DataFrame)
        assert len(transformed) == 5
        # Verify data integrity after transformation
        assert transformed.iloc[0]["category"] == "Electronics"

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_excel_config):
        """Test the complete ingestion pipeline with live Excel data."""
        adapter = ExcelAdapter(sample_excel_config)
        payload = await adapter.process()

        # Check data
        assert isinstance(payload.data, pd.DataFrame)
        assert len(payload.data) == 5
        assert "price" in payload.data.columns
        assert "rating" in payload.data.columns

        # Check metadata
        assert payload.metadata.source_id == "test-excel-source"
        assert payload.metadata.adapter_type == "ExcelAdapter"
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
            "path": "tests/fixtures/nonexistent.xlsx",
        }
        adapter = ExcelAdapter(config)

        with pytest.raises(CollectionError):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_missing_config_raises_error(self):
        """Test that missing required config raises CollectionError."""
        config = {"source_id": "test", "source_type": "file"}
        adapter = ExcelAdapter(config)

        with pytest.raises(CollectionError, match="path not provided"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_excel_with_numeric_data(self, sample_excel_config):
        """Test Excel with numeric columns."""
        adapter = ExcelAdapter(sample_excel_config)
        payload = await adapter.process()

        # Check that numeric columns are preserved
        assert payload.data["price"].dtype in ["int64", "float64"]
        assert payload.data["stock"].dtype in ["int64", "float64"]
        assert payload.data["rating"].dtype in ["int64", "float64"]
        assert payload.data["price"].max() > 900  # Laptop price

    @pytest.mark.asyncio
    async def test_excel_default_sheet(self):
        """Test reading Excel with default sheet (first sheet)."""
        config = {
            "source_id": "test-default-sheet",
            "source_type": "file",
            "path": "tests/fixtures/sample.xlsx",
            # No sheet_name specified, should use default (0)
        }
        adapter = ExcelAdapter(config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) > 0

    @pytest.mark.asyncio
    async def test_collect_with_chunked_read_options(self, sample_excel_config):
        """Ensure chunked read options still load full Excel content."""

        config = {**sample_excel_config}
        config["read_options"] = {"chunk_size": 1024}

        adapter = ExcelAdapter(config)
        raw_data = await adapter.collect()

        assert isinstance(raw_data, pd.DataFrame)
        assert len(raw_data) == 5

    @pytest.mark.asyncio
    async def test_collect_respects_max_bytes_limit(self, sample_excel_config):
        """Chunked reader should guard against oversized Excel files."""

        config = {**sample_excel_config}
        config["read_options"] = {"max_bytes": 512}

        adapter = ExcelAdapter(config)

        with pytest.raises(CollectionError, match="max_bytes"):
            await adapter.collect()
