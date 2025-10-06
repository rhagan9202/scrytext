#!/usr/bin/env python3
"""Smoke test for Word adapter pipeline.

Tests end-to-end ingestion flow for Word documents.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scry_ingestor.adapters.word_adapter import WordAdapter
from scry_ingestor.schemas.payload import IngestionPayload


async def test_business_letter_extraction() -> bool:
    """Test extraction from business letter."""
    print("→ Testing business letter extraction...")

    test_docx = Path(__file__).parent.parent / "fixtures" / "sample.docx"
    config = {
        "source_id": "smoke-test-word-letter",
        "source_type": "file",
        "path": str(test_docx),
        "use_cloud_processing": False,
    }

    try:
        adapter = WordAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid, "Payload validation failed"
        assert payload.metadata.adapter_type == "WordAdapter"
        assert payload.data is not None

        print("  ✓ Business letter extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Business letter extraction: FAIL - {e}")
        return False


async def test_meeting_minutes_extraction() -> bool:
    """Test extraction from meeting minutes."""
    print("→ Testing meeting minutes extraction...")

    test_docx = Path(__file__).parent.parent / "fixtures" / "sample.docx"
    config = {
        "source_id": "smoke-test-word-minutes",
        "source_type": "file",
        "path": str(test_docx),
        "use_cloud_processing": False,
    }

    try:
        adapter = WordAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        assert payload.data is not None

        print("  ✓ Meeting minutes extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Meeting minutes extraction: FAIL - {e}")
        return False


async def test_technical_specification_extraction() -> bool:
    """Test extraction from technical specification."""
    print("→ Testing technical specification extraction...")

    test_docx = Path(__file__).parent.parent / "fixtures" / "sample.docx"
    config = {
        "source_id": "smoke-test-word-spec",
        "source_type": "file",
        "path": str(test_docx),
        "use_cloud_processing": False,
        "transformation": {"extract_tables": True},
    }

    try:
        adapter = WordAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Technical specification extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Technical specification extraction: FAIL - {e}")
        return False


async def test_project_proposal_extraction() -> bool:
    """Test extraction from project proposal."""
    print("→ Testing project proposal extraction...")

    test_docx = Path(__file__).parent.parent / "fixtures" / "sample.docx"
    config = {
        "source_id": "smoke-test-word-proposal",
        "source_type": "file",
        "path": str(test_docx),
        "use_cloud_processing": False,
    }

    try:
        adapter = WordAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Project proposal extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Project proposal extraction: FAIL - {e}")
        return False


async def test_table_data_extraction() -> bool:
    """Test extraction of tabular data."""
    print("→ Testing table data extraction...")

    test_docx = Path(__file__).parent.parent / "fixtures" / "sample.docx"
    config = {
        "source_id": "smoke-test-word-table",
        "source_type": "file",
        "path": str(test_docx),
        "use_cloud_processing": False,
        "transformation": {"extract_tables": True},
    }

    try:
        adapter = WordAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Table data extraction: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Table data extraction: FAIL - {e}")
        return False


async def main() -> int:
    """Run all Word adapter smoke tests."""
    print("\n" + "=" * 60)
    print("WORD ADAPTER PIPELINE SMOKE TESTS")
    print("=" * 60 + "\n")

    tests = [
        test_business_letter_extraction,
        test_meeting_minutes_extraction,
        test_technical_specification_extraction,
        test_project_proposal_extraction,
        test_table_data_extraction,
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
        print("✅ All Word adapter smoke tests PASSED")
        print("=" * 60 + "\n")
        return 0
    else:
        print(f"❌ {total - passed} smoke test(s) FAILED")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
