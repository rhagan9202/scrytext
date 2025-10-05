"""CLI utility for summarizing PDF ingestion results."""
import asyncio
import json
from pathlib import Path
from typing import Any

import click

from scry_ingestor.adapters.pdf_adapter import PDFAdapter
from scry_ingestor.schemas.payload import IngestionPayload


def format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}TB"


def print_summary(payload: IngestionPayload) -> None:
    """Print formatted summary of ingestion payload."""
    click.echo("\n" + "=" * 70)
    click.echo("PDF INGESTION SUMMARY")
    click.echo("=" * 70)

    # Metadata section
    click.echo("\n📋 DOCUMENT METADATA")
    click.echo("-" * 70)
    metadata = payload.data.get("metadata", {})
    click.echo(f"  Title:        {metadata.get('title') or 'N/A'}")
    click.echo(f"  Author:       {metadata.get('author') or 'N/A'}")
    click.echo(f"  Creator:      {metadata.get('creator') or 'N/A'}")
    click.echo(f"  Created:      {metadata.get('created') or 'N/A'}")
    click.echo(f"  Modified:     {metadata.get('modified') or 'N/A'}")
    click.echo(f"  Page Count:   {metadata.get('page_count', 0)}")
    click.echo(f"  Format:       {metadata.get('format') or 'N/A'}")
    click.echo(f"  Encrypted:    {metadata.get('is_encrypted', False)}")

    # Content summary
    click.echo("\n📊 CONTENT SUMMARY")
    click.echo("-" * 70)
    summary = payload.data.get("summary", {})
    click.echo(f"  Total Pages:          {summary.get('total_pages', 0)}")
    click.echo(f"  Total Text Length:    {summary.get('total_text_length', 0):,} chars")
    click.echo(f"  Average Text/Page:    {summary.get('average_text_per_page', 0):.1f} chars")
    click.echo(f"  Total Tables:         {summary.get('total_tables', 0)}")
    click.echo(f"  Total Images:         {summary.get('total_images', 0)}")

    # Trimming statistics
    trimmed_pages = summary.get("trimmed_pages", 0)
    trimmed_chars = summary.get("trimmed_characters", 0)
    if trimmed_pages > 0:
        click.echo("\n  ⚠️  Text Trimming Applied:")
        click.echo(f"      Pages Trimmed:      {trimmed_pages}")
        click.echo(f"      Characters Removed: {trimmed_chars:,}")

    # Per-page breakdown
    pages = payload.data.get("pages", [])
    if pages:
        click.echo("\n📄 PER-PAGE BREAKDOWN")
        click.echo("-" * 70)
        for page in pages:
            page_num = page.get("page_number", "?")
            text_len = len(page.get("text", ""))
            tables = len(page.get("tables", []))
            images = len(page.get("images", []))
            truncated = page.get("text_truncated", False)

            status = " [TRIMMED]" if truncated else ""
            page_text = f"  Page {page_num}: {text_len:,} chars, "
            page_text += f"{tables} tables, {images} images{status}"
            click.echo(page_text)

            if truncated:
                original = page.get("text_original_length", 0)
                click.echo(f"           (original: {original:,} chars)")

    # Processing metadata
    click.echo("\n⚙️  PROCESSING DETAILS")
    click.echo("-" * 70)
    click.echo(f"  Source ID:        {payload.metadata.source_id}")
    click.echo(f"  Adapter:          {payload.metadata.adapter_type}")
    click.echo(f"  Processing Mode:  {payload.metadata.processing_mode}")
    click.echo(f"  Duration:         {payload.metadata.processing_duration_ms} ms")
    click.echo(f"  Timestamp:        {payload.metadata.timestamp}")
    if payload.metadata.correlation_id:
        click.echo(f"  Correlation ID:   {payload.metadata.correlation_id}")

    # Validation status
    click.echo("\n✅ VALIDATION")
    click.echo("-" * 70)
    validation = payload.validation
    status_icon = "✅" if validation.is_valid else "❌"
    click.echo(f"  Status: {status_icon} {'VALID' if validation.is_valid else 'INVALID'}")

    if validation.errors:
        click.echo("\n  Errors:")
        for error in validation.errors:
            click.echo(f"    • {error}")

    if validation.warnings:
        click.echo("\n  Warnings:")
        for warning in validation.warnings:
            click.echo(f"    • {warning}")

    if validation.metrics:
        click.echo("\n  Quality Metrics:")
        for key, value in validation.metrics.items():
            click.echo(f"    {key}: {value}")

    click.echo("\n" + "=" * 70 + "\n")


def print_json_output(payload: IngestionPayload) -> None:
    """Print payload as JSON (excluding large text content)."""
    output = {
        "metadata": {
            "source_id": payload.metadata.source_id,
            "adapter_type": payload.metadata.adapter_type,
            "processing_duration_ms": payload.metadata.processing_duration_ms,
            "processing_mode": payload.metadata.processing_mode,
            "timestamp": payload.metadata.timestamp,
            "correlation_id": payload.metadata.correlation_id,
        },
        "document_metadata": payload.data.get("metadata", {}),
        "summary": payload.data.get("summary", {}),
        "validation": {
            "is_valid": payload.validation.is_valid,
            "errors": payload.validation.errors,
            "warnings": payload.validation.warnings,
            "metrics": payload.validation.metrics,
        },
        "page_count": len(payload.data.get("pages", [])),
        "pages": [
            {
                "page_number": p.get("page_number"),
                "text_length": len(p.get("text", "")),
                "text_truncated": p.get("text_truncated", False),
                "text_original_length": p.get("text_original_length"),
                "table_count": len(p.get("tables", [])),
                "image_count": len(p.get("images", [])),
                "width": p.get("width"),
                "height": p.get("height"),
            }
            for p in payload.data.get("pages", [])
        ],
    }

    click.echo(json.dumps(output, indent=2))


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option(
    "--extract-tables",
    is_flag=True,
    help="Extract tables from PDF (slower, more comprehensive)",
)
@click.option(
    "--extract-images",
    is_flag=True,
    help="Extract image metadata from PDF",
)
@click.option(
    "--layout-mode",
    is_flag=True,
    help="Preserve layout in text extraction",
)
@click.option(
    "--max-chars-per-page",
    type=int,
    help="Limit text characters per page (for large documents)",
)
@click.option(
    "--page-range",
    type=str,
    help="Process specific page range (format: start,end, e.g., '0,5')",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output summary as JSON instead of formatted text",
)
@click.option(
    "--source-id",
    default=None,
    help="Source identifier for tracking (defaults to filename)",
)
def summarize_pdf(
    pdf_path: str,
    extract_tables: bool,
    extract_images: bool,
    layout_mode: bool,
    max_chars_per_page: int | None,
    page_range: str | None,
    output_json: bool,
    source_id: str,
) -> None:
    """
    Summarize PDF ingestion results without storing full text content.

    This utility processes a PDF document using the PDFAdapter and displays
    a comprehensive summary including metadata, content statistics, validation
    results, and per-page breakdowns.

    Examples:

        # Basic summary
        scry-pdf-summary document.pdf

        # With table extraction
        scry-pdf-summary --extract-tables document.pdf

        # Process first 10 pages only
        scry-pdf-summary --page-range 0,10 large_document.pdf

        # Limit text per page to 5000 chars
        scry-pdf-summary --max-chars-per-page 5000 document.pdf

        # JSON output for automation
        scry-pdf-summary --json document.pdf
    """
    # Build configuration
    config: dict[str, Any] = {
        "source_id": source_id or Path(pdf_path).stem,
        "source_type": "file",
        "path": pdf_path,
        "use_cloud_processing": False,
        "transformation": {
            "extract_metadata": True,
            "extract_tables": extract_tables,
            "extract_images": extract_images,
            "layout_mode": layout_mode,
            "combine_pages": True,
        },
    }

    if max_chars_per_page:
        config["transformation"]["max_text_chars_per_page"] = max_chars_per_page

    if page_range:
        try:
            start, end = map(int, page_range.split(","))
            config["transformation"]["page_range"] = [start, end]
        except ValueError:
            click.echo("Error: --page-range must be in format 'start,end' (e.g., '0,5')", err=True)
            raise click.Abort()

    # Process PDF
    try:
        if not output_json:
            click.echo(f"Processing PDF: {pdf_path}")
            click.echo("Please wait...")

        async def process() -> IngestionPayload:
            adapter = PDFAdapter(config)
            return await adapter.process()

        payload = asyncio.run(process())

        # Display results
        if output_json:
            print_json_output(payload)
        else:
            print_summary(payload)

    except Exception as e:
        click.echo(f"\n❌ Error processing PDF: {str(e)}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    summarize_pdf()
