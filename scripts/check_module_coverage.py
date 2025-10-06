#!/usr/bin/env python3
"""Check module-level coverage thresholds for critical modules.

This script validates that critical modules meet minimum coverage requirements.
Usage: python check_module_coverage.py --threshold 60 --coverage-file coverage.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Critical modules that must meet higher coverage thresholds
CRITICAL_MODULES = {
    "scry_ingestor/adapters": "Data source adapters (core ingestion logic)",
    "scry_ingestor/api/routes": "API endpoints (external interface)",
    "scry_ingestor/tasks": "Celery task handlers (async processing)",
    "scry_ingestor/schemas": "Data validation schemas",
    "scry_ingestor/models": "Database models and repositories",
}


def load_coverage_data(coverage_file: Path) -> dict[str, Any]:
    """Load coverage data from JSON file."""
    with open(coverage_file) as f:
        return json.load(f)


def calculate_module_coverage(
    coverage_data: dict[str, Any],
    module_prefix: str,
) -> tuple[int, int, float]:
    """Calculate coverage for a specific module.

    Returns:
        Tuple of (covered_lines, total_lines, coverage_percentage)
    """
    files_data = coverage_data.get("files", {})

    covered_lines = 0
    total_lines = 0

    for file_path, file_data in files_data.items():
        # Normalize path separators for cross-platform compatibility
        normalized_path = file_path.replace("\\", "/")

        if normalized_path.startswith(module_prefix):
            summary = file_data.get("summary", {})
            covered_lines += summary.get("covered_lines", 0)
            total_lines += summary.get("num_statements", 0)

    if total_lines == 0:
        return 0, 0, 0.0

    coverage_pct = (covered_lines / total_lines) * 100
    return covered_lines, total_lines, coverage_pct


def check_thresholds(
    coverage_file: Path,
    threshold: float,
) -> tuple[bool, list[str]]:
    """Check if all critical modules meet coverage threshold.

    Returns:
        Tuple of (all_passed, failure_messages)
    """
    coverage_data = load_coverage_data(coverage_file)

    failures: list[str] = []
    all_passed = True

    print("\n" + "=" * 80)
    print("MODULE-LEVEL COVERAGE ANALYSIS")
    print("=" * 80)
    print(f"Minimum threshold: {threshold}%\n")

    for module_prefix, description in CRITICAL_MODULES.items():
        covered, total, coverage_pct = calculate_module_coverage(
            coverage_data,
            module_prefix,
        )

        status = "✅ PASS" if coverage_pct >= threshold else "❌ FAIL"
        print(f"{status} | {module_prefix:40s} | {coverage_pct:5.1f}% ({covered}/{total})")
        print(f"      {description}")

        if coverage_pct < threshold:
            all_passed = False
            failures.append(f"{module_prefix}: {coverage_pct:.1f}% " f"(threshold: {threshold}%)")

    # Check overall coverage
    totals = coverage_data.get("totals", {})
    overall_covered = totals.get("covered_lines", 0)
    overall_total = totals.get("num_statements", 1)
    overall_pct = (overall_covered / overall_total) * 100

    print("\n" + "-" * 80)
    print(f"Overall Coverage: {overall_pct:.1f}% ({overall_covered}/{overall_total})")
    print("=" * 80 + "\n")

    return all_passed, failures


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check module-level coverage thresholds")
    parser.add_argument(
        "--threshold",
        type=float,
        required=True,
        help="Minimum coverage percentage required per module",
    )
    parser.add_argument(
        "--coverage-file",
        type=Path,
        default=Path("coverage.json"),
        help="Path to coverage.json file (default: coverage.json)",
    )

    args = parser.parse_args()

    if not args.coverage_file.exists():
        print(f"❌ Coverage file not found: {args.coverage_file}", file=sys.stderr)
        return 1

    all_passed, failures = check_thresholds(args.coverage_file, args.threshold)

    if not all_passed:
        print("\n❌ Coverage check failed for the following modules:")
        for failure in failures:
            print(f"   - {failure}")
        print("\nPlease add tests to meet the minimum coverage threshold.\n")
        return 1

    print("✅ All critical modules meet the coverage threshold!\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
