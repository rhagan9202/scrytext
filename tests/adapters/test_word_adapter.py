"""Tests for WordAdapter using live test data."""

import pytest

from scry_ingestor.adapters.word_adapter import WordAdapter
from scry_ingestor.exceptions import CollectionError, ConfigurationError


@pytest.fixture
def sample_word_config(tmp_path):
    """Configuration for sample Word document."""
    return {
        "source_id": "test-word-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.docx",
        "use_cloud_processing": False,
    }


@pytest.fixture
def word_config_with_validation(tmp_path):
    """Configuration with strict validation rules."""
    return {
        "source_id": "test-word-strict",
        "source_type": "file",
        "path": "tests/fixtures/sample.docx",
        "validation": {
            "min_paragraphs": 3,
            "min_words": 10,
            "allow_empty": False,
        },
    }


@pytest.fixture
def word_config_with_tables(tmp_path):
    """Configuration with table extraction enabled."""
    return {
        "source_id": "test-word-tables",
        "source_type": "file",
        "path": "tests/fixtures/sample.docx",
        "transformation": {
            "extract_tables": True,
            "extract_metadata": True,
        },
    }


class TestWordAdapter:
    """Test suite for WordAdapter with live fixtures."""

    @pytest.mark.asyncio
    async def test_collect_from_file(self, sample_word_config):
        """Test collecting data from Word document using live test data."""
        adapter = WordAdapter(sample_word_config)
        raw_data = await adapter.collect()

        # Check that document was loaded (returns Document object directly)
        assert raw_data is not None
        # Check it has expected attributes of a DocxDocument
        assert hasattr(raw_data, 'paragraphs')
        assert hasattr(raw_data, 'core_properties')

    @pytest.mark.asyncio
    async def test_collect_missing_file(self):
        """Test collecting from non-existent file raises error."""
        config = {
            "source_id": "test-missing",
            "source_type": "file",
            "path": "tests/fixtures/nonexistent.docx",
        }
        adapter = WordAdapter(config)

        with pytest.raises(CollectionError, match="File not found"):
            await adapter.collect()

    @pytest.mark.asyncio
    async def test_collect_invalid_file_type(self):
        """Test collecting from non-Word file raises error with helpful message."""
        config = {
            "source_id": "test-invalid",
            "source_type": "file",
            "path": "tests/fixtures/sample.json",  # Use existing JSON file
        }
        adapter = WordAdapter(config)

        with pytest.raises(CollectionError) as exc_info:
            await adapter.collect()

        error_message = str(exc_info.value)
        assert "Unsupported file type" in error_message
        assert ".docx" in error_message
        assert "convert" in error_message.lower()

    @pytest.mark.asyncio
    async def test_validate_valid_document(self, sample_word_config):
        """Test validation of valid Word document."""
        adapter = WordAdapter(sample_word_config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is True
        assert len(validation.errors) == 0
        assert "paragraph_count" in validation.metrics
        assert validation.metrics["paragraph_count"] > 0
        assert "word_count" in validation.metrics
        assert validation.metrics["word_count"] > 0
        assert "text_length_chars" in validation.metrics
        assert "table_count" in validation.metrics

    @pytest.mark.asyncio
    async def test_validate_with_min_requirements(self, word_config_with_validation):
        """Test validation with minimum requirements."""
        adapter = WordAdapter(word_config_with_validation)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        # Should pass because sample document has enough content
        assert validation.is_valid is True
        assert validation.metrics["paragraph_count"] >= 3
        assert validation.metrics["word_count"] >= 10

    @pytest.mark.asyncio
    async def test_validate_insufficient_paragraphs(self):
        """Test validation fails with insufficient paragraphs."""
        config = {
            "source_id": "test-strict",
            "source_type": "file",
            "path": "tests/fixtures/sample.docx",
            "validation": {
                "min_paragraphs": 1000,  # Unrealistically high
            },
        }
        adapter = WordAdapter(config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is False
        assert any("paragraphs" in error for error in validation.errors)

    @pytest.mark.asyncio
    async def test_validate_missing_required_tables(self, sample_word_config):
        """Validation should fail when required table counts are unmet."""

        config = {
            **sample_word_config,
            "validation": {
                "require_tables": True,
                "min_tables": 5,
            },
        }

        adapter = WordAdapter(config)
        raw_data = await adapter.collect()
        validation = await adapter.validate(raw_data)

        assert validation.is_valid is False
        assert any("tables" in error for error in validation.errors)

    @pytest.mark.asyncio
    async def test_transform_basic(self, sample_word_config):
        """Test basic transformation of Word document."""
        adapter = WordAdapter(sample_word_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert isinstance(transformed, dict)
        assert "text" in transformed
        assert "paragraph_count" in transformed
        assert "metadata" in transformed
        assert len(transformed["text"]) > 0
        assert transformed["paragraph_count"] > 0

    @pytest.mark.asyncio
    async def test_transform_with_metadata(self, sample_word_config):
        """Test transformation extracts document metadata."""
        sample_word_config["transformation"] = {"extract_metadata": True}
        adapter = WordAdapter(sample_word_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert "metadata" in transformed
        metadata = transformed["metadata"]
        assert "author" in metadata
        assert metadata["author"] == "Test Author"
        assert "title" in metadata
        assert metadata["title"] == "Test Document"

    @pytest.mark.asyncio
    async def test_transform_with_tables(self, word_config_with_tables):
        """Test transformation with table extraction."""
        adapter = WordAdapter(word_config_with_tables)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        assert "tables" in transformed
        assert len(transformed["tables"]) > 0
        # Check first table structure
        first_table = transformed["tables"][0]
        assert len(first_table) > 0  # Has rows
        assert len(first_table[0]) > 0  # Has columns

    @pytest.mark.asyncio
    async def test_transform_paragraph_separator(self, sample_word_config):
        """Test transformation with custom paragraph separator."""
        sample_word_config["transformation"] = {
            "paragraph_separator": "\n\n",
        }
        adapter = WordAdapter(sample_word_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        # Check that double newlines are used
        assert "\n\n" in transformed["text"]

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_word_config):
        """Test the complete ingestion pipeline with live data."""
        adapter = WordAdapter(sample_word_config)
        payload = await adapter.process()

        # Check data
        assert isinstance(payload.data, dict)
        assert "text" in payload.data
        assert len(payload.data["text"]) > 0

        # Check metadata (access as attributes, not dict)
        assert payload.metadata.source_id == "test-word-source"
        assert payload.metadata.adapter_type == "WordAdapter"
        assert payload.metadata.processing_mode == "local"
        assert payload.metadata.processing_duration_ms >= 0

        # Check validation
        assert payload.validation.is_valid is True
        assert len(payload.validation.errors) == 0

    @pytest.mark.asyncio
    async def test_process_with_correlation_id(self, sample_word_config):
        """Test process pipeline includes correlation ID."""
        sample_word_config["correlation_id"] = "test-correlation-123"
        adapter = WordAdapter(sample_word_config)
        payload = await adapter.process()

        assert payload.metadata.correlation_id == "test-correlation-123"

    @pytest.mark.asyncio
    async def test_text_content_accuracy(self, sample_word_config):
        """Test that extracted text matches expected content."""
        adapter = WordAdapter(sample_word_config)
        raw_data = await adapter.collect()
        transformed = await adapter.transform(raw_data)

        text = transformed["text"]
        # Check for known content from sample document
        assert "first paragraph" in text.lower()
        assert "second paragraph" in text.lower()
        assert "third paragraph" in text.lower()

    @pytest.mark.asyncio
    async def test_unsupported_format_error_message(self):
        """Test that unsupported formats (.doc, .txt, etc.) provide clear error messages."""
        config = {
            "source_id": "test-unsupported",
            "source_type": "file",
            "path": "tests/fixtures/sample.csv",
        }
        adapter = WordAdapter(config)

        with pytest.raises(CollectionError) as exc_info:
            await adapter.collect()

        error_message = str(exc_info.value)
        assert "Unsupported file type" in error_message
        assert ".docx" in error_message
        assert "convert" in error_message.lower()

    @pytest.mark.asyncio
    async def test_doc_file_rejected(self):
        """Test that .doc files are rejected with helpful message."""
        config = {
            "source_id": "test-doc-file",
            "source_type": "file",
            "path": "tests/fixtures/sample.doc",
        }
        adapter = WordAdapter(config)

        with pytest.raises(CollectionError) as exc_info:
            await adapter.collect()

        error_message = str(exc_info.value)
        assert "Unsupported file type" in error_message
        assert ".doc" in error_message
        assert "convert" in error_message.lower()

    @pytest.mark.asyncio
    async def test_collect_with_chunked_read_options(self, sample_word_config):
        """Ensure chunked read options still load Word document."""

        config = {**sample_word_config}
        config["read_options"] = {"chunk_size": 256}

        adapter = WordAdapter(config)
        raw_data = await adapter.collect()

        assert raw_data is not None
        assert len(raw_data.paragraphs) > 0

    @pytest.mark.asyncio
    async def test_collect_respects_max_bytes_limit(self, sample_word_config):
        """Chunked reader should guard against oversized Word files."""

        config = {**sample_word_config}
        config["read_options"] = {"max_bytes": 128}

        adapter = WordAdapter(config)

        with pytest.raises(CollectionError, match="max_bytes"):
            await adapter.collect()

    def test_invalid_transformation_config_raises_configuration_error(
        self, sample_word_config
    ) -> None:
        """Invalid transformation options should be rejected eagerly."""

        sample_word_config["transformation"] = {"paragraph_separator": ""}

        with pytest.raises(ConfigurationError):
            WordAdapter(sample_word_config)

    @pytest.mark.asyncio
    async def test_collect_with_invalid_read_options_logs_warning(
        self, sample_word_config, caplog
    ):
        """Ensure non-mapping read_options emit a warning for Word files."""

        config = {**sample_word_config}
        config["read_options"] = "invalid"

        adapter = WordAdapter(config)
        with caplog.at_level("WARNING", logger="scry_ingestor.utils.file_readers"):
            raw_data = await adapter.collect()

        assert raw_data is not None
        assert any("not a mapping" in message for message in caplog.messages)

    @pytest.mark.asyncio
    async def test_collect_with_invalid_binary_read_option_values_warns(
        self, sample_word_config, caplog
    ):
        """Invalid binary options should trigger fallback warnings."""

        config = {**sample_word_config}
        config["read_options"] = {
            "chunk_size": 0,
            "max_bytes": "none",
            "unexpected": 99,
        }

        adapter = WordAdapter(config)
        with caplog.at_level("WARNING", logger="scry_ingestor.utils.file_readers"):
            raw_data = await adapter.collect()

        assert raw_data is not None
        messages = " ".join(caplog.messages)
        assert "must be greater than zero" in messages
        assert "Invalid max_bytes value" in messages
        assert "Ignoring unsupported" in messages
