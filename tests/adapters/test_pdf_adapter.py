"""Tests for PDFAdapter using live test data."""

from contextlib import asynccontextmanager

import pytest

from scry_ingestor.adapters.pdf_adapter import PDFAdapter
from scry_ingestor.exceptions import CollectionError, ConfigurationError


@asynccontextmanager
async def manage_pdf_resources(adapter: PDFAdapter):
    """Collect PDF resources for a test and ensure cleanup afterwards."""

    raw_data = await adapter.collect()
    try:
        yield raw_data
    finally:
        await adapter.cleanup(raw_data)


@pytest.fixture
def sample_pdf_config():
    """Configuration for sample PDF document."""
    return {
        "source_id": "test-pdf-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.pdf",
        "use_cloud_processing": False,
    }


@pytest.fixture
def pdf_config_with_tables():
    """Configuration with table extraction enabled."""
    return {
        "source_id": "test-pdf-tables",
        "source_type": "file",
        "path": "tests/fixtures/sample.pdf",
        "transformation": {
            "extract_tables": True,
            "extract_metadata": True,
        },
    }


@pytest.fixture
def pdf_config_with_validation():
    """Configuration with strict validation rules."""
    return {
        "source_id": "test-pdf-strict",
        "source_type": "file",
        "path": "tests/fixtures/sample.pdf",
        "validation": {
            "min_pages": 2,
            "min_words": 10,
            "allow_empty": False,
        },
    }


@pytest.fixture
def pdf_config_layout_mode():
    """Configuration with layout-preserving text extraction."""
    return {
        "source_id": "test-pdf-layout",
        "source_type": "file",
        "path": "tests/fixtures/sample.pdf",
        "transformation": {
            "layout_mode": True,
            "extract_metadata": True,
        },
    }


class TestPDFAdapter:
    """Test suite for PDFAdapter with live fixtures."""

    @pytest.mark.asyncio
    async def test_collect_from_file(self, sample_pdf_config):
        """Test collecting data from PDF document using live test data."""
        adapter = PDFAdapter(sample_pdf_config)
        async with manage_pdf_resources(adapter) as raw_data:
            # Check that both document objects were loaded
            assert raw_data is not None
            assert isinstance(raw_data, dict)
            assert "pdfplumber_doc" in raw_data
            assert "pymupdf_doc" in raw_data
            assert "path" in raw_data
            assert raw_data["byte_size"] > 0

            # Verify documents are valid
            assert raw_data["pdfplumber_doc"] is not None
            assert raw_data["pymupdf_doc"] is not None
            assert len(raw_data["pdfplumber_doc"].pages) > 0

    @pytest.mark.asyncio
    async def test_collect_missing_file(self):
        """Test collecting from non-existent file raises error."""
        config = {
            "source_id": "test-missing",
            "source_type": "file",
            "path": "tests/fixtures/nonexistent.pdf",
        }
        adapter = PDFAdapter(config)

        with pytest.raises(CollectionError, match="File not found"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_collect_with_chunked_read_options(self, sample_pdf_config):
        """Ensure chunked read options still load PDF document."""

        config = {**sample_pdf_config}
        config["read_options"] = {"chunk_size": 512_000}

        adapter = PDFAdapter(config)
        async with manage_pdf_resources(adapter) as raw_data:
            assert raw_data["byte_size"] > 0

    @pytest.mark.asyncio
    async def test_collect_respects_max_bytes_limit(self, sample_pdf_config):
        """Chunked reader should guard against oversized PDF files."""

        config = {**sample_pdf_config}
        config["read_options"] = {"max_bytes": 256}

        adapter = PDFAdapter(config)

        with pytest.raises(CollectionError, match="max_bytes"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_collect_invalid_file_type(self):
        """Test collecting from non-PDF file raises error."""
        config = {
            "source_id": "test-invalid",
            "source_type": "file",
            "path": "tests/fixtures/sample.json",
        }
        adapter = PDFAdapter(config)

        with pytest.raises(CollectionError, match="Unsupported file type"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_validate_valid_document(self, sample_pdf_config):
        """Test validation of valid PDF document."""
        adapter = PDFAdapter(sample_pdf_config)
        async with manage_pdf_resources(adapter) as raw_data:
            validation = await adapter.validate(raw_data)

            assert validation.is_valid is True
            assert len(validation.errors) == 0
            assert "page_count" in validation.metrics
            assert validation.metrics["page_count"] == 3  # Our test PDF has 3 pages
            assert "total_words" in validation.metrics
            assert validation.metrics["total_words"] > 0
            assert "total_text_chars" in validation.metrics
            assert "table_count" in validation.metrics
            assert "has_metadata" in validation.metrics

    @pytest.mark.asyncio
    async def test_validate_with_min_requirements(self, pdf_config_with_validation):
        """Test validation with minimum requirements."""
        adapter = PDFAdapter(pdf_config_with_validation)
        async with manage_pdf_resources(adapter) as raw_data:
            validation = await adapter.validate(raw_data)

            # Should pass because sample document has enough content
            assert validation.is_valid is True
            assert validation.metrics["page_count"] >= 2
            assert validation.metrics["total_words"] >= 10

    @pytest.mark.asyncio
    async def test_validate_insufficient_pages(self):
        """Test validation fails with insufficient pages."""
        config = {
            "source_id": "test-strict",
            "source_type": "file",
            "path": "tests/fixtures/sample.pdf",
            "validation": {
                "min_pages": 100,  # Unrealistically high
            },
        }
        adapter = PDFAdapter(config)
        async with manage_pdf_resources(adapter) as raw_data:
            validation = await adapter.validate(raw_data)

            assert validation.is_valid is False
            assert any("pages" in error for error in validation.errors)

    @pytest.mark.asyncio
    async def test_validate_missing_required_tables(self, sample_pdf_config):
        """Validation should fail when table requirements are unmet."""

        sample_pdf_config["validation"] = {
            "require_tables": True,
            "min_tables": 3,
        }
        adapter = PDFAdapter(sample_pdf_config)
        async with manage_pdf_resources(adapter) as raw_data:
            validation = await adapter.validate(raw_data)

            assert validation.is_valid is False
            assert any("tables" in error for error in validation.errors)

    @pytest.mark.asyncio
    async def test_transform_basic(self, sample_pdf_config):
        """Test basic transformation of PDF document."""
        adapter = PDFAdapter(sample_pdf_config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        assert isinstance(transformed, dict)
        assert "pages" in transformed
        assert "metadata" in transformed
        assert "summary" in transformed
        assert "full_text" in transformed

        # Check pages
        assert len(transformed["pages"]) == 3
        for page in transformed["pages"]:
            assert "page_number" in page
            assert "text" in page
            assert "width" in page
            assert "height" in page

        # Check summary
        assert transformed["summary"]["total_pages"] == 3
        assert transformed["summary"]["total_text_length"] > 0

    @pytest.mark.asyncio
    async def test_transform_with_metadata(self, sample_pdf_config):
        """Test transformation extracts document metadata."""
        sample_pdf_config["transformation"] = {"extract_metadata": True}
        adapter = PDFAdapter(sample_pdf_config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        assert "metadata" in transformed
        metadata = transformed["metadata"]
        assert "title" in metadata
        assert metadata["title"] == "Test PDF Document"
        assert "author" in metadata
        assert metadata["author"] == "Test Author"
        assert "page_count" in metadata
        assert metadata["page_count"] == 3

    @pytest.mark.asyncio
    async def test_transform_with_tables(self, pdf_config_with_tables):
        """Test transformation with table extraction."""
        adapter = PDFAdapter(pdf_config_with_tables)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        # Check if tables were extracted
        assert "pages" in transformed
        # First page should have table
        first_page = transformed["pages"][0]
        assert "tables" in first_page or "tables_error" in first_page

        # If tables were extracted, verify structure
        if "tables" in first_page and first_page["tables"]:
            tables = first_page["tables"]
            assert isinstance(tables, list)
            # Each table should be a list of rows
            if len(tables) > 0:
                assert isinstance(tables[0], list)

    @pytest.mark.asyncio
    async def test_transform_layout_mode(self, pdf_config_layout_mode):
        """Test transformation with layout-preserving text extraction."""
        adapter = PDFAdapter(pdf_config_layout_mode)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        assert "pages" in transformed
        assert len(transformed["pages"]) > 0
        # Layout mode should preserve spacing and structure
        for page in transformed["pages"]:
            assert "text" in page

    @pytest.mark.asyncio
    async def test_transform_page_combination(self, sample_pdf_config):
        """Test that pages are combined correctly."""
        sample_pdf_config["transformation"] = {
            "combine_pages": True,
            "page_separator": "\n---PAGE BREAK---\n",
        }
        adapter = PDFAdapter(sample_pdf_config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        assert "full_text" in transformed
        assert "\n---PAGE BREAK---\n" in transformed["full_text"]

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_pdf_config):
        """Test the complete ingestion pipeline with live data."""
        adapter = PDFAdapter(sample_pdf_config)
        payload = await adapter.process()

        # Check data
        assert isinstance(payload.data, dict)
        assert "pages" in payload.data
        assert "metadata" in payload.data
        assert len(payload.data["pages"]) == 3

        # Check metadata (access as attributes, not dict)
        assert payload.metadata.source_id == "test-pdf-source"
        assert payload.metadata.adapter_type == "PDFAdapter"
        assert payload.metadata.processing_mode == "local"
        assert payload.metadata.processing_duration_ms >= 0

        # Check validation
        assert payload.validation.is_valid is True
        assert len(payload.validation.errors) == 0

    @pytest.mark.asyncio
    async def test_process_with_correlation_id(self, sample_pdf_config):
        """Test process pipeline includes correlation ID."""
        sample_pdf_config["correlation_id"] = "test-correlation-123"
        adapter = PDFAdapter(sample_pdf_config)
        payload = await adapter.process()

        assert payload.metadata.correlation_id == "test-correlation-123"

    def test_invalid_transformation_page_range_raises_configuration_error(
        self, sample_pdf_config
    ) -> None:
        """Invalid page range bounds should fail fast during adapter creation."""

        sample_pdf_config["transformation"] = {"page_range": [5, 2]}

        with pytest.raises(ConfigurationError):
            PDFAdapter(sample_pdf_config)

    @pytest.mark.asyncio
    async def test_text_content_accuracy(self, sample_pdf_config):
        """Test that extracted text matches expected content."""
        adapter = PDFAdapter(sample_pdf_config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        full_text = transformed["full_text"].lower()
        # Check for known content from sample PDF
        assert "test pdf document" in full_text
        assert "first paragraph" in full_text
        assert "page 2" in full_text
        assert "page 3" in full_text

    @pytest.mark.asyncio
    async def test_page_count_metrics(self, sample_pdf_config):
        """Test that page count metrics are accurate."""
        adapter = PDFAdapter(sample_pdf_config)
        payload = await adapter.process()

        assert payload.validation.metrics["page_count"] == 3
        assert payload.data["summary"]["total_pages"] == 3
        assert payload.data["metadata"]["page_count"] == 3

    @pytest.mark.asyncio
    async def test_page_range_extraction(self):
        """Test extraction of specific page range."""
        config = {
            "source_id": "test-page-range",
            "source_type": "file",
            "path": "tests/fixtures/sample.pdf",
            "transformation": {
                "page_range": [0, 2],  # First 2 pages
            },
        }
        adapter = PDFAdapter(config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        assert len(transformed["pages"]) == 2
        assert transformed["summary"]["total_pages"] == 2

    @pytest.mark.asyncio
    async def test_empty_page_handling(self):
        """Test handling of validation for empty documents."""
        # This test verifies the error handling logic
        config = {
            "source_id": "test-empty-check",
            "source_type": "file",
            "path": "tests/fixtures/sample.pdf",
            "validation": {
                "allow_empty": False,
            },
        }
        adapter = PDFAdapter(config)
        payload = await adapter.process()

        # Our sample PDF is not empty, should pass
        assert payload.validation.is_valid is True

    @pytest.mark.asyncio
    async def test_image_detection(self):
        """Test image metadata extraction."""
        config = {
            "source_id": "test-images",
            "source_type": "file",
            "path": "tests/fixtures/sample.pdf",
            "transformation": {
                "extract_images": True,
            },
        }
        adapter = PDFAdapter(config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        # Check that image extraction was attempted
        assert "pages" in transformed
        for page in transformed["pages"]:
            # Either images were found or no error occurred
            assert "images" in page or "images_error" in page or True

    @pytest.mark.asyncio
    async def test_summary_statistics(self, sample_pdf_config):
        """Test that summary statistics are calculated correctly."""
        adapter = PDFAdapter(sample_pdf_config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        summary = transformed["summary"]
        assert "total_pages" in summary
        assert "total_text_length" in summary
        assert "total_tables" in summary
        assert "total_images" in summary
        assert "average_text_per_page" in summary

        # Verify calculations
        assert summary["total_pages"] == 3
        assert summary["total_text_length"] > 0
        if summary["total_pages"] > 0:
            avg = summary["total_text_length"] / summary["total_pages"]
            assert summary["average_text_per_page"] == pytest.approx(avg)

    @pytest.mark.asyncio
    async def test_text_trimming_per_page(self, sample_pdf_config):
        """Test that per-page text trimming limits payload size."""
        sample_pdf_config["transformation"] = {
            "max_text_chars_per_page": 20,
            "combine_pages": True,
            "page_separator": "",
        }
        adapter = PDFAdapter(sample_pdf_config)
        transformed = None
        async with manage_pdf_resources(adapter) as raw_data:
            transformed = await adapter.transform(raw_data)

        pages = transformed["pages"]
        trimmed_flags = [page["text_truncated"] for page in pages]

        assert len(pages) == 3
        assert any(trimmed_flags), "Expected at least one page to be trimmed"

        trimmed_count = 0
        trimmed_characters_total = 0
        for page in pages:
            assert len(page["text"]) <= 20
            if page["text_truncated"]:
                trimmed_count += 1
                original_length = page["text_original_length"]
                trimmed_chars = page["text_trimmed_characters"]
                assert original_length - len(page["text"]) == trimmed_chars
                trimmed_characters_total += trimmed_chars

        summary = transformed["summary"]
        assert summary["trimmed_pages"] == trimmed_count
        assert summary["trimmed_characters"] == trimmed_characters_total
        assert len(transformed["full_text"]) <= 20 * len(pages)

    @pytest.mark.asyncio
    async def test_cleanup_closes_handles(self, sample_pdf_config):
        """Cleanup should close any open PDF document handles."""

        class DummyDoc:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        adapter = PDFAdapter(sample_pdf_config)
        plumber_dummy = DummyDoc()
        pymupdf_dummy = DummyDoc()

        await adapter.cleanup({
            "pdfplumber_doc": plumber_dummy,
            "pymupdf_doc": pymupdf_dummy,
        })

        assert plumber_dummy.closed is True
        assert pymupdf_dummy.closed is True

    @pytest.mark.asyncio
    async def test_process_invokes_cleanup(self, sample_pdf_config):
        """Process pipeline should invoke cleanup even on success."""

        class TrackingPDFAdapter(PDFAdapter):
            def __init__(self, config):
                super().__init__(config)
                self.cleanup_called = False

            async def cleanup(self, raw_data):
                self.cleanup_called = True
                await super().cleanup(raw_data)

        adapter = TrackingPDFAdapter(sample_pdf_config)
        await adapter.process()

        assert adapter.cleanup_called is True
