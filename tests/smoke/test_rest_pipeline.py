#!/usr/bin/env python3
"""Smoke test for REST/JSON data pipeline.

Tests end-to-end ingestion flow for JSON/REST data sources.
"""

from __future__ import annotations

import asyncio
import json

from scry_ingestor.adapters.json_adapter import JSONAdapter
from scry_ingestor.schemas.payload import IngestionPayload
from tests.fixtures.synthetic import rest_fixtures


async def test_simple_json_ingestion() -> bool:
    """Test basic JSON REST response ingestion."""
    print("→ Testing simple JSON ingestion...")

    json_data = json.dumps(rest_fixtures.VALID_USER_API_RESPONSE)
    config = {
        "source_id": "smoke-test-rest-json",
        "source_type": "string",
        "data": json_data,
        "use_cloud_processing": False,
    }

    try:
        adapter = JSONAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid, "Payload validation failed"
        assert payload.metadata.adapter_type == "JSONAdapter"
        assert payload.metadata.source_id == "smoke-test-rest-json"
        assert len(payload.validation.errors) == 0

        print("  ✓ Simple JSON ingestion: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Simple JSON ingestion: FAIL - {e}")
        return False


async def test_paginated_data_ingestion() -> bool:
    """Test paginated API response ingestion."""
    print("→ Testing paginated data ingestion...")

    json_data = json.dumps(rest_fixtures.PAGINATED_PRODUCTS_PAGE_1)
    config = {
        "source_id": "smoke-test-rest-paginated",
        "source_type": "string",
        "data": json_data,
        "use_cloud_processing": False,
    }

    try:
        adapter = JSONAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        assert "products" in json.dumps(payload.data)

        print("  ✓ Paginated data ingestion: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Paginated data ingestion: FAIL - {e}")
        return False


async def test_unicode_data_handling() -> bool:
    """Test Unicode character handling."""
    print("→ Testing Unicode data handling...")

    json_data = json.dumps(rest_fixtures.UNICODE_DATA, ensure_ascii=False)
    config = {
        "source_id": "smoke-test-rest-unicode",
        "source_type": "string",
        "data": json_data,
        "use_cloud_processing": False,
    }

    try:
        adapter = JSONAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Unicode data handling: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Unicode data handling: FAIL - {e}")
        return False


async def test_null_fields_handling() -> bool:
    """Test handling of null and missing fields."""
    print("→ Testing null/missing fields handling...")

    json_data = json.dumps(rest_fixtures.NULL_AND_MISSING_FIELDS)
    config = {
        "source_id": "smoke-test-rest-nulls",
        "source_type": "string",
        "data": json_data,
        "use_cloud_processing": False,
    }

    try:
        adapter = JSONAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Null/missing fields handling: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Null/missing fields handling: FAIL - {e}")
        return False


async def test_nested_data_structures() -> bool:
    """Test deeply nested data structure handling."""
    print("→ Testing nested data structures...")

    json_data = json.dumps(rest_fixtures.DEEPLY_NESTED_DATA)
    config = {
        "source_id": "smoke-test-rest-nested",
        "source_type": "string",
        "data": json_data,
        "use_cloud_processing": False,
    }

    try:
        adapter = JSONAdapter(config)
        payload: IngestionPayload = await adapter.process()

        assert payload.validation.is_valid
        print("  ✓ Nested data structures: PASS")
        return True

    except Exception as e:
        print(f"  ✗ Nested data structures: FAIL - {e}")
        return False


async def main() -> int:
    """Run all REST adapter smoke tests."""
    print("\n" + "=" * 60)
    print("REST ADAPTER PIPELINE SMOKE TESTS")
    print("=" * 60 + "\n")

    tests = [
        test_simple_json_ingestion,
        test_paginated_data_ingestion,
        test_unicode_data_handling,
        test_null_fields_handling,
        test_nested_data_structures,
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
        print("✅ All REST adapter smoke tests PASSED")
        print("=" * 60 + "\n")
        return 0
    else:
        print(f"❌ {total - passed} smoke test(s) FAILED")
        print("=" * 60 + "\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    raise SystemExit(exit_code)
