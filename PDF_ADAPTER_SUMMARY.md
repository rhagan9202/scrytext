# PDF Adapter Summary (State-of-the-Art Extraction)

## Overview
The PDF adapter combines `pdfplumber` and `pymupdf` to deliver high-fidelity ingestion for complex PDF documents, supporting text, tables, metadata, images, and optional OCR.

## Key Features
- **Hybrid Extraction Pipeline**: pdfplumber for table/text layout, PyMuPDF for metadata and images.
- **Per-Page Processing**: Collects dimensions, text length, table/image counts per page.
- **Payload Controls**: `max_text_chars_per_page` trims large pages while retaining audit metadata.
- **OCR Ready**: Optional Tesseract integration for scanned documents (`ocr.enabled`).
- **Validation Metrics**: Page count, word count, table detection, encryption flags.
- **Summary Statistics**: Aggregates tables, images, trimmed characters for dashboards.

## Configuration Highlights (`config/pdf_adapter.yaml`)
```yaml
transformation:
  extract_metadata: true
  extract_tables: false
  extract_images: false
  layout_mode: false
  combine_pages: true
  page_separator: "\n\n"
  max_text_chars_per_page: null

ocr:
  enabled: false
  language: "eng"

table_settings:
  vertical_strategy: "lines"
  horizontal_strategy: "lines"
```

## CLI Utility (`scry-pdf-summary`)
```bash
# Basic usage
scry-pdf-summary report.pdf

# With table extraction and per-page trimming
scry-pdf-summary --extract-tables --max-chars-per-page 3000 report.pdf

# JSON output (ideal for dashboards)
scry-pdf-summary --json --page-range 0,10 report.pdf > report-summary.json
```

## Sample Summary Output
```
PDF INGESTION SUMMARY
...
Total Tables: 4
Trimmed Pages: 2 (3,500 characters removed)
Validation: ✅ VALID (warnings: scanned pages without OCR)
```

## Testing
- `tests/adapters/test_pdf_adapter.py` now includes trimming, table extraction, layout, OCR guidance coverage.
- CLI validated via `poetry run scry-pdf-summary` with fixture documents.

## Security & Licensing Notes
- PyMuPDF is AGPLv3. Keep dependency updates and CVE monitoring in CI.
- Document OCR prerequisites (Tesseract binary and language packs) for deployments.
