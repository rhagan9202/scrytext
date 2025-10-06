#!/usr/bin/env python3
"""Smoke test for PDF adapter pipeline.

Tests end-to-end ingestion flow for PDF documents.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scry_ingestor.adapters.pdf_adapter import PDFAdapter
from scry_ingestor.schemas.payload import IngestionPayload


async def test_simple_invoice_extraction() -> bool:
    """Test extraction from simple invoice document."""
    print("→ Testing simple invoice extraction...")

    test_pdf = Path(__file__).parent.parent / "fixtures" / "sample.pdf"
    config = {
        "source_id": "smoke-test-pdf-invoice",
        "source_type": "file",
        "path": str(test_pdf),
        "use_cloud_processing": False,
    }

    try:
        adapter = PDFAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid, "Payload validation failed"
        assert payload.metadata.adapter_type == "PDFAdapter"
        assert payload.data is not None

        print("  ✓ Simple invoice extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Simple invoice extraction: FAIL - {e}")
        return False


async def test_multi_page_report_extraction() -> bool:
    """Test extraction from multi-page report."""
    print("→ Testing multi-page report extraction...")

    test_pdf = Path(__file__).parent.parent / "fixtures" / "sample.pdf"
    config = {
        "source_id": "smoke-test-pdf-report",
        "source_type": "file",
        "path": str(test_pdf),
        "use_cloud_processing": False,
    }

    try:
        adapter = PDFAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        assert payload.data is not None

        print("  ✓ Multi-page report extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Multi-page report extraction: FAIL - {e}")
        return False


async def test_technical_documentation_extraction() -> bool:
    """Test extraction from technical documentation."""
    print("→ Testing technical documentation extraction...")

    test_pdf = Path(__file__).parent.parent / "fixtures" / "sample.pdf"
    config = {
        "source_id": "smoke-test-pdf-technical",
        "source_type": "file",
        "path": str(test_pdf),
        "use_cloud_processing": False,
        "transformation": {"extract_tables": True},
    }

    try:
        adapter = PDFAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Technical documentation extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Technical documentation extraction: FAIL - {e}")
        return False


async def test_table_data_extraction() -> bool:
    """Test extraction of tabular data."""
    print("→ Testing table data extraction...")

    test_pdf = Path(__file__).parent.parent / "fixtures" / "sample.pdf"
    config = {
        "source_id": "smoke-test-pdf-table",
        "source_type": "file",
        "path": str(test_pdf),
        "use_cloud_processing": False,
        "transformation": {"extract_tables": True},
    }

    try:
        adapter = PDFAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Table data extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Table data extraction: FAIL - {e}")
        return False


async def test_unicode_character_handling() -> bool:
    """Test Unicode character handling."""
    print("→ Testing Unicode character handling...")

    test_pdf = Path(__file__).parent.parent / "fixtures" / "sample.pdf"
    config = {
        "source_id": "smoke-test-pdf-unicode",
        "source_type": "file",
        "path": str(test_pdf),
        "use_cloud_processing": False,
    }

    try:
        adapter = PDFAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Unicode character handling: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Unicode character handling: FAIL - {e}")
        return False


async def main() -> int:
    """Run all PDF adapter smoke tests."""
    print("\n" + "=" * 60)
    print("PDF ADAPTER PIPELINE SMOKE TESTS")
    print("=" * 60 + "\n")

    tests = [
        test_simple_invoice_extraction,
        test_multi_page_report_extraction,
        test_technical_documentation_extraction,
        test_table_data_extraction,
        test_unicode_character_handling,
    ]

    results = []
    for test_func in tests:
        result = await test_func()
        results.append(result)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")

    if passed == total:
        print("✅ All PDF adapter smoke tests PASSED")
        print("=" * 60 + "\n")
        return 0
    else:
        print(f"❌ {total - passed} smoke test(s) FAILED")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
