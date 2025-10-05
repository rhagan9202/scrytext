"""Tests for the PDF summary CLI module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from click.testing import CliRunner

from scry_ingestor.cli.pdf_summary import (
    format_bytes,
    print_json_output,
    print_summary,
    summarize_pdf,
)
from scry_ingestor.schemas.payload import (
    IngestionMetadata,
    IngestionPayload,
    ValidationResult,
)


class TestFormatBytes:
    """Test suite for format_bytes function."""

    def test_bytes(self):
        """Test formatting bytes."""
        assert format_bytes(512) == "512.0B"
        assert format_bytes(1023) == "1023.0B"

    def test_kilobytes(self):
        """Test formatting kilobytes."""
        assert format_bytes(1024) == "1.0KB"
        assert format_bytes(2048) == "2.0KB"
        assert format_bytes(1536) == "1.5KB"

    def test_megabytes(self):
        """Test formatting megabytes."""
        assert format_bytes(1024 * 1024) == "1.0MB"
        assert format_bytes(1024 * 1024 * 2) == "2.0MB"
        assert format_bytes(1024 * 1024 + 512 * 1024) == "1.5MB"

    def test_gigabytes(self):
        """Test formatting gigabytes."""
        assert format_bytes(1024 * 1024 * 1024) == "1.0GB"
        assert format_bytes(1024 * 1024 * 1024 * 2) == "2.0GB"

    def test_terabytes(self):
        """Test formatting terabytes."""
        tb = 1024 * 1024 * 1024 * 1024
        assert format_bytes(tb) == "1.0TB"
        assert format_bytes(tb * 2) == "2.0TB"

    def test_zero(self):
        """Test zero bytes."""
        assert format_bytes(0) == "0.0B"

    def test_small_values(self):
        """Test very small values."""
        assert format_bytes(1) == "1.0B"
        assert format_bytes(100) == "100.0B"


class TestPrintSummary:
    """Test suite for print_summary function."""

    def create_sample_payload(self) -> IngestionPayload:
        """Create a sample payload for testing."""
        return IngestionPayload(
            data={
                "metadata": {
                    "title": "Test Document",
                    "author": "Test Author",
                    "creator": "Test Creator",
                    "created": "2023-01-01",
                    "modified": "2023-01-02",
                    "page_count": 5,
                    "format": "PDF 1.4",
                    "is_encrypted": False,
                },
                "summary": {
                    "total_pages": 5,
                    "total_text_length": 1000,
                    "average_text_per_page": 200.0,
                    "total_tables": 2,
                    "total_images": 1,
                    "content_extraction_time": 1500,
                    "processing_warnings": 0,
                    "trimmed_pages": 0,
                    "trimmed_characters": 0,
                },
                "pages": [
                    {
                        "page_number": 1,
                        "text": "Sample page text",
                        "text_length": 16,
                        "tables": [],
                        "images": [],
                        "width": 612.0,
                        "height": 792.0,
                    }
                ],
                "full_text": "Sample full text content",
            },
            metadata=IngestionMetadata(
                source_id="test-pdf",
                adapter_type="PDFAdapter",
                processing_duration_ms=2000,
                processing_mode="local",
                timestamp="2023-01-01T12:00:00Z",
                correlation_id="test-123",
            ),
            validation=ValidationResult(
                is_valid=True,
                errors=[],
                warnings=["Minor warning"],
                metrics={"text_quality": 0.95, "table_count": 2},
            ),
        )

    @patch("click.echo")
    def test_print_summary_complete(self, mock_echo):
        """Test printing complete summary with all sections."""
        payload = self.create_sample_payload()
        print_summary(payload)

        # Should have called click.echo multiple times
        assert mock_echo.call_count > 0
        
        # Check that the function didn't crash
        calls = [str(call) for call in mock_echo.call_args_list]
        # Just verify the function executed without errors
        assert len(calls) > 0

    @patch("click.echo")
    def test_print_summary_minimal_data(self, mock_echo):
        """Test printing summary with minimal data."""
        payload = IngestionPayload(
            data={},
            metadata=IngestionMetadata(
                source_id="minimal",
                adapter_type="PDFAdapter",
                processing_duration_ms=500,
                processing_mode="local",
                timestamp="2023-01-01T12:00:00Z",
                correlation_id="minimal-123",
            ),
            validation=ValidationResult(is_valid=True, errors=[], warnings=[], metrics={}),
        )

        print_summary(payload)

        calls = [call.args[0] for call in mock_echo.call_args_list]
        # Should handle missing data gracefully
        assert any("N/A" in call for call in calls)
        assert any("0" in call for call in calls)

    @patch("click.echo")
    def test_print_summary_with_errors(self, mock_echo):
        """Test printing summary with validation errors."""
        payload = self.create_sample_payload()
        payload.validation.is_valid = False
        payload.validation.errors = ["Critical error", "Another error"]

        print_summary(payload)

        calls = [call.args[0] for call in mock_echo.call_args_list]
        assert any("❌ INVALID" in call for call in calls)
        assert any("Critical error" in call for call in calls)
        assert any("Another error" in call for call in calls)


class TestPrintJsonOutput:
    """Test suite for print_json_output function."""

    def create_sample_payload(self) -> IngestionPayload:
        """Create a sample payload for testing."""
        return IngestionPayload(
            data={
                "metadata": {"title": "Test Document", "page_count": 2},
                "summary": {"total_pages": 2, "total_text_length": 500},
                "pages": [
                    {
                        "page_number": 1,
                        "text": "Page 1 text",
                        "tables": [],
                        "images": [],
                        "width": 612.0,
                        "height": 792.0,
                    },
                    {
                        "page_number": 2,
                        "text": "Page 2 text",
                        "text_truncated": True,
                        "text_original_length": 1000,
                        "tables": [{"data": "table"}],
                        "images": [{"type": "jpeg"}],
                        "width": 612.0,
                        "height": 792.0,
                    },
                ],
            },
            metadata=IngestionMetadata(
                source_id="test-json",
                adapter_type="PDFAdapter",
                processing_duration_ms=1000,
                processing_mode="local",
                timestamp="2023-01-01T12:00:00Z",
                correlation_id="json-123",
            ),
            validation=ValidationResult(
                is_valid=True,
                errors=[],
                warnings=["Warning"],
                metrics={"quality": 0.9},
            ),
        )

    @patch("click.echo")
    def test_print_json_output_structure(self, mock_echo):
        """Test JSON output structure and content."""
        payload = self.create_sample_payload()
        print_json_output(payload)

        # Get the printed JSON
        mock_echo.assert_called_once()
        json_str = mock_echo.call_args[0][0]
        output = json.loads(json_str)

        # Verify structure
        assert "metadata" in output
        assert "document_metadata" in output
        assert "summary" in output
        assert "validation" in output
        assert "page_count" in output
        assert "pages" in output

        # Verify metadata
        assert output["metadata"]["source_id"] == "test-json"
        assert output["metadata"]["adapter_type"] == "PDFAdapter"
        assert output["metadata"]["correlation_id"] == "json-123"

        # Verify page data
        assert output["page_count"] == 2
        assert len(output["pages"]) == 2
        assert output["pages"][0]["page_number"] == 1
        assert output["pages"][0]["text_length"] == 11  # len("Page 1 text")
        assert output["pages"][1]["text_truncated"] is True
        assert output["pages"][1]["table_count"] == 1
        assert output["pages"][1]["image_count"] == 1

        # Verify validation
        assert output["validation"]["is_valid"] is True
        assert output["validation"]["warnings"] == ["Warning"]


class TestSummarizePdfCli:
    """Test suite for the CLI command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.sample_payload = IngestionPayload(
            data={
                "metadata": {"title": "CLI Test PDF", "page_count": 1},
                "summary": {"total_pages": 1, "total_text_length": 100},
                "pages": [{"page_number": 1, "text": "Sample text"}],
            },
            metadata=IngestionMetadata(
                source_id="cli-test",
                adapter_type="PDFAdapter",
                processing_duration_ms=500,
                processing_mode="local",
                timestamp="2023-01-01T12:00:00Z",
                correlation_id="cli-123",
            ),
            validation=ValidationResult(is_valid=True, errors=[], warnings=[], metrics={}),
        )

    def test_cli_help(self):
        """Test CLI help output."""
        result = self.runner.invoke(summarize_pdf, ["--help"])
        assert result.exit_code == 0
        assert "Summarize PDF ingestion results" in result.output
        assert "--extract-tables" in result.output
        assert "--json" in result.output

    @patch("scry_ingestor.cli.pdf_summary.PDFAdapter")
    def test_cli_basic_execution(self, mock_adapter_class):
        """Test basic CLI execution."""
        # Mock adapter and its process method
        mock_adapter = Mock()
        mock_adapter.process = AsyncMock(return_value=self.sample_payload)
        mock_adapter_class.return_value = mock_adapter

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = self.runner.invoke(summarize_pdf, [tmp_path])
            assert result.exit_code == 0
            assert "Processing PDF" in result.output

            # Verify adapter was configured correctly
            mock_adapter_class.assert_called_once()
            config = mock_adapter_class.call_args[0][0]
            assert config["source_type"] == "file"
            assert config["path"] == tmp_path
            assert config["transformation"]["extract_metadata"] is True
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("scry_ingestor.cli.pdf_summary.PDFAdapter")
    def test_cli_with_options(self, mock_adapter_class):
        """Test CLI with various options."""
        mock_adapter = Mock()
        mock_adapter.process = AsyncMock(return_value=self.sample_payload)
        mock_adapter_class.return_value = mock_adapter

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = self.runner.invoke(
                summarize_pdf,
                [
                    tmp_path,
                    "--extract-tables",
                    "--extract-images",
                    "--layout-mode",
                    "--max-chars-per-page",
                    "5000",
                    "--page-range",
                    "0,10",
                    "--source-id",
                    "custom-id",
                ],
            )
            assert result.exit_code == 0

            # Verify configuration
            config = mock_adapter_class.call_args[0][0]
            assert config["source_id"] == "custom-id"
            assert config["transformation"]["extract_tables"] is True
            assert config["transformation"]["extract_images"] is True
            assert config["transformation"]["layout_mode"] is True
            assert config["transformation"]["max_text_chars_per_page"] == 5000
            assert config["transformation"]["page_range"] == [0, 10]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("scry_ingestor.cli.pdf_summary.PDFAdapter")
    @patch("scry_ingestor.cli.pdf_summary.print_json_output")
    def test_cli_json_output(self, mock_print_json, mock_adapter_class):
        """Test CLI JSON output."""
        mock_adapter = Mock()
        mock_adapter.process = AsyncMock(return_value=self.sample_payload)
        mock_adapter_class.return_value = mock_adapter

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = self.runner.invoke(summarize_pdf, [tmp_path, "--json"])
            assert result.exit_code == 0

            # Should not have progress messages in JSON mode
            assert "Processing PDF" not in result.output
            # JSON print function should be called
            mock_print_json.assert_called_once()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_cli_invalid_page_range(self):
        """Test CLI with invalid page range."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = self.runner.invoke(
                summarize_pdf, [tmp_path, "--page-range", "invalid"]
            )
            assert result.exit_code == 1
            assert "must be in format 'start,end'" in result.output
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @patch("scry_ingestor.cli.pdf_summary.PDFAdapter")
    def test_cli_adapter_error(self, mock_adapter_class):
        """Test CLI handling adapter errors."""
        mock_adapter_class.side_effect = Exception("Adapter failed")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = self.runner.invoke(summarize_pdf, [tmp_path])
            assert result.exit_code == 1
            assert "Error processing PDF" in result.output
            assert "Adapter failed" in result.output
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_cli_default_source_id(self):
        """Test CLI generates source ID from filename when not specified."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("scry_ingestor.cli.pdf_summary.PDFAdapter") as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.process = AsyncMock(return_value=self.sample_payload)
                mock_adapter_class.return_value = mock_adapter

                result = self.runner.invoke(summarize_pdf, [tmp_path])
                assert result.exit_code == 0

                # Should use filename as source_id
                config = mock_adapter_class.call_args[0][0]
                assert Path(tmp_path).stem in config["source_id"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)
