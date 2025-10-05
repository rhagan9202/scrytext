"""Unstructured adapter for PDF documents using state-of-the-art extraction."""

import io
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf  # PyMuPDF (fitz)
from pydantic import ValidationError as PydanticValidationError

from ..exceptions import CollectionError, ConfigurationError
from ..schemas.payload import ValidationResult
from ..schemas.transformations import PDFTransformationConfig
from ..utils.file_readers import read_binary_file, resolve_binary_read_options
from .base import BaseAdapter


class PDFAdapter(BaseAdapter):
    """
    Adapter for collecting and processing unstructured data from PDF documents.

    Uses best-in-class libraries:
    - pdfplumber: Superior table extraction, text with layout, metadata
    - pymupdf (PyMuPDF): High-performance text extraction, OCR support, images

    Supports:
    - Text extraction (with optional layout preservation)
    - Table extraction (automatic detection and structured output)
    - Metadata extraction (author, title, dates, page count, etc.)
    - Image detection and metadata
    - Multi-page documents
    - Both text-based and scanned PDFs (with OCR configuration)

    Features:
    - Automatic table detection using pdfplumber's advanced algorithms
    - Layout-aware text extraction
    - Per-page processing for large documents
    - Configurable extraction strategies
    """

    SUPPORTED_FORMAT = ".pdf"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            self._transformation = PDFTransformationConfig.model_validate(
                config.get("transformation") or {}
            )
        except PydanticValidationError as exc:
            raise ConfigurationError(
                f"Invalid PDF transformation configuration: {exc}"
            ) from exc

    async def collect(self) -> dict[str, Any]:
        """
        Collect raw data from PDF document using hybrid approach.

        Returns pdfplumber PDF object and pymupdf Document for processing.

        Returns:
            Dictionary containing:
            - pdfplumber_doc: pdfplumber.PDF object for table/text extraction
            - pymupdf_doc: pymupdf.Document object for metadata/images
            - path: Original file path

        Raises:
            CollectionError: If document collection fails
        """
        source_type = self.config.get("source_type", "file")

        try:
            if source_type == "file":
                file_path = self.config.get("path")
                if not file_path:
                    raise CollectionError("File path not provided in config")

                path = Path(file_path)
                if not path.exists():
                    raise CollectionError(f"File not found: {file_path}")

                file_format = path.suffix.lower()
                if file_format != self.SUPPORTED_FORMAT:
                    raise CollectionError(
                        f"Unsupported file type: {file_format}. "
                        f"Only .pdf files are supported."
                    )

                chunk_size, max_bytes = resolve_binary_read_options(
                    self.config.get("read_options")
                )
                data_bytes = await self._run_in_thread(
                    read_binary_file,
                    file_path,
                    chunk_size=chunk_size,
                    max_bytes=max_bytes,
                )

                # Open with both libraries for different strengths without blocking the loop
                pdfplumber_doc = await self._run_in_thread(
                    pdfplumber.open,
                    io.BytesIO(data_bytes),
                )
                pymupdf_doc = await self._run_in_thread(
                    pymupdf.open,
                    stream=data_bytes,
                    filetype="pdf",
                )

                return {
                    "pdfplumber_doc": pdfplumber_doc,
                    "pymupdf_doc": pymupdf_doc,
                    "path": str(path),
                    "byte_size": len(data_bytes),
                }

            else:
                raise CollectionError(f"Unsupported source type: {source_type}")

        except OSError as e:
            raise CollectionError(f"Failed to read PDF document: {e}")
        except CollectionError:
            raise
        except Exception as e:
            raise CollectionError(f"Failed to parse PDF document: {e}") from e

    async def validate(self, raw_data: dict[str, Any]) -> ValidationResult:
        """
        Validate the PDF document structure and content.

        Args:
            raw_data: Dictionary from collect() with pdfplumber and pymupdf docs

        Returns:
            ValidationResult with quality metrics
        """

        return await self._run_in_thread(self._validate_sync, raw_data)

    def _validate_sync(self, raw_data: dict[str, Any]) -> ValidationResult:
        """Synchronous validation logic executed in a worker thread."""
        errors: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, Any] = {}

        try:
            pdfplumber_doc = raw_data["pdfplumber_doc"]
            pymupdf_doc = raw_data["pymupdf_doc"]

            # Basic document metrics
            page_count = len(pdfplumber_doc.pages)
            metrics["page_count"] = page_count

            # Validate page count
            min_pages = self.config.get("validation", {}).get("min_pages", 0)
            if page_count < min_pages:
                errors.append(
                    f"Document has {page_count} pages, minimum required: {min_pages}"
                )

            # Extract text from all pages for validation
            total_chars = 0
            total_words = 0
            has_images = False
            table_count = 0

            for page_num, page in enumerate(pdfplumber_doc.pages, 1):
                try:
                    # Get text
                    text = page.extract_text()
                    if text:
                        total_chars += len(text)
                        total_words += len(text.split())

                    # Count tables
                    tables = page.find_tables()
                    table_count += len(tables)

                    # Check for images
                    if page.images:
                        has_images = True

                except Exception as exc:
                    warnings.append(f"Error processing page {page_num}: {str(exc)}")

            metrics["total_text_chars"] = total_chars
            metrics["total_words"] = total_words
            metrics["table_count"] = table_count
            metrics["has_images"] = has_images

            # PyMuPDF metadata
            try:
                metadata = pymupdf_doc.metadata
                if metadata:
                    metrics["has_metadata"] = True
                    metrics["is_encrypted"] = pymupdf_doc.is_encrypted
            except Exception:
                metrics["has_metadata"] = False

            # Validation rules from config
            validation_config = self.config.get("validation", {})
            min_words = validation_config.get("min_words", 0)
            allow_empty = validation_config.get("allow_empty", False)
            require_tables = validation_config.get("require_tables", False)
            min_tables = validation_config.get("min_tables")

            # Check for empty document
            if total_chars == 0 and not allow_empty:
                errors.append("Document contains no extractable text")

            # Check minimum words
            if total_words < min_words:
                errors.append(
                    f"Document has {total_words} words, minimum required: {min_words}"
                )

            # Check table requirement
            if require_tables and table_count == 0:
                errors.append("Document contains no tables, but tables are required")

            if isinstance(min_tables, int) and table_count < min_tables:
                errors.append(
                    f"Document has {table_count} tables, minimum required: {min_tables}"
                )

            # Warnings for potentially problematic documents
            if total_chars == 0 and has_images:
                warnings.append(
                    "Document contains images but no text - may be scanned. "
                    "Consider enabling OCR in transformation settings."
                )

            if pymupdf_doc.is_encrypted:
                warnings.append("Document is encrypted/password-protected")

            is_valid = len(errors) == 0

        except Exception as exc:
            errors.append(f"Validation error: {str(exc)}")
            is_valid = False

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    async def transform(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """
        Transform PDF document into standardized format.

        Args:
            raw_data: Dictionary from collect() with pdfplumber and pymupdf docs

        Returns:
            Dictionary with extracted text, metadata, tables, and images
        """

        return await self._run_in_thread(self._transform_sync, raw_data)

    def _transform_sync(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Synchronous transformation logic executed in a worker thread."""
        transformation_config = self._transformation
        pdfplumber_doc = raw_data["pdfplumber_doc"]
        pymupdf_doc = raw_data["pymupdf_doc"]

        result: dict[str, Any] = {
            "pages": [],
            "metadata": {},
            "summary": {},
        }

        # Extract metadata using pymupdf (more comprehensive)
        if transformation_config.extract_metadata:
            metadata = pymupdf_doc.metadata or {}
            result["metadata"] = {
                "title": metadata.get("title"),
                "author": metadata.get("author"),
                "subject": metadata.get("subject"),
                "keywords": metadata.get("keywords"),
                "creator": metadata.get("creator"),
                "producer": metadata.get("producer"),
                "created": metadata.get("creationDate"),
                "modified": metadata.get("modDate"),
                "page_count": pymupdf_doc.page_count,
                "is_encrypted": pymupdf_doc.is_encrypted,
                "format": f"PDF {pymupdf_doc.metadata.get('format', 'Unknown')}",
            }

        # Process each page
        extract_tables = transformation_config.extract_tables
        extract_images = transformation_config.extract_images
        layout_mode = transformation_config.layout_mode
        page_range = transformation_config.page_range
        text_trim_limit = transformation_config.max_text_chars_per_page

        pages_to_process = pdfplumber_doc.pages
        if page_range:
            start, end = page_range
            pages_to_process = pdfplumber_doc.pages[start:end]

        total_text_length = 0
        total_tables = 0
        total_images = 0
        trimmed_pages = 0
        trimmed_characters = 0

        for page_num, page in enumerate(pages_to_process, 1):
            page_data: dict[str, Any] = {
                "page_number": page_num,
                "text": "",
                "width": page.width,
                "height": page.height,
            }

            # Extract text with pdfplumber (better layout handling)
            page_text = ""
            trimmed_amount = 0
            try:
                if layout_mode:
                    # Preserve layout
                    page_text = page.extract_text(layout=True) or ""
                else:
                    # Simple text extraction
                    page_text = page.extract_text() or ""

            except Exception as exc:
                page_data["error"] = f"Text extraction failed: {str(exc)}"
                page_text = ""

            original_length = len(page_text)
            if text_trim_limit and original_length > text_trim_limit:
                trimmed_amount = original_length - text_trim_limit
                page_text = page_text[:text_trim_limit]
                page_data["text_truncated"] = True
                page_data["text_original_length"] = original_length
                page_data["text_trimmed_characters"] = trimmed_amount
                trimmed_pages += 1
                trimmed_characters += trimmed_amount
            else:
                page_data["text_truncated"] = False

            page_data["text"] = page_text
            total_text_length += len(page_text)

            # Extract tables with pdfplumber (best-in-class)
            if extract_tables:
                try:
                    tables = page.extract_tables()
                    if tables:
                        page_data["tables"] = tables
                        total_tables += len(tables)
                except Exception as exc:
                    page_data["tables_error"] = f"Table extraction failed: {str(exc)}"

            # Extract image metadata (not raw image data)
            if extract_images:
                try:
                    images = page.images
                    if images:
                        page_data["images"] = [
                            {
                                "x0": img["x0"],
                                "y0": img["y0"],
                                "x1": img["x1"],
                                "y1": img["y1"],
                                "width": img["width"],
                                "height": img["height"],
                            }
                            for img in images
                        ]
                        total_images += len(images)
                except Exception as exc:
                    page_data["images_error"] = f"Image detection failed: {str(exc)}"

            result["pages"].append(page_data)

        # Summary statistics
        result["summary"] = {
            "total_pages": len(pages_to_process),
            "total_text_length": total_text_length,
            "total_tables": total_tables,
            "total_images": total_images,
            "average_text_per_page": (
                total_text_length / len(pages_to_process) if pages_to_process else 0
            ),
            "trimmed_pages": trimmed_pages,
            "trimmed_characters": trimmed_characters,
        }

        # Optionally combine all page text
        if transformation_config.combine_pages:
            page_separator = transformation_config.page_separator
            result["full_text"] = page_separator.join(
                [p["text"] for p in result["pages"] if p["text"]]
            )

        return result

    async def cleanup(self, raw_data: dict[str, Any]) -> None:
        """Close any open PDF document handles once processing completes."""

        await self._run_in_thread(self._cleanup_sync, raw_data)

    def _cleanup_sync(self, raw_data: dict[str, Any]) -> None:
        """Synchronously close PDF handles, ignoring secondary errors."""

        for key in ("pdfplumber_doc", "pymupdf_doc"):
            doc = raw_data.get(key)
            if doc and hasattr(doc, "close"):
                try:
                    doc.close()
                except Exception:
                    continue
