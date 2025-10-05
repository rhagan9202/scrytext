"""Pytest configuration - no path manipulation, rely on proper package installation."""

from __future__ import annotations

import os

import pytest

from scry_ingestor.models.base import reset_engine
from scry_ingestor.utils.config import get_settings


@pytest.fixture(autouse=True)
def _ensure_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory):
    """Guarantee SCRY_DATABASE_URL is available for runtime validation."""

    if os.getenv("SCRY_DATABASE_URL") is None:
        db_path = tmp_path_factory.mktemp("sqlite-db") / "ingestion.sqlite"
        monkeypatch.setenv("SCRY_DATABASE_URL", f"sqlite:///{db_path}")
    if os.getenv("SCRY_API_KEYS") is None:
        monkeypatch.setenv("SCRY_API_KEYS", '["test-key"]')

    get_settings.cache_clear()
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def sample_json_config():
    """Fixture providing sample JSON adapter configuration."""
    return {
        "source_id": "test-json-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.json",
        "use_cloud_processing": False,
    }


@pytest.fixture
def sample_json_string_config():
    """Fixture providing JSON string adapter configuration."""
    return {
        "source_id": "test-json-string",
        "source_type": "string",
        "data": '{"name": "test", "value": 42, "nested": {"key": "value"}}',
        "use_cloud_processing": False,
    }


@pytest.fixture
def sample_csv_config():
    """Fixture providing sample CSV adapter configuration."""
    return {
        "source_id": "test-csv-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.csv",
        "use_cloud_processing": False,
    }


@pytest.fixture
def sample_csv_string_config():
    """Fixture providing CSV string adapter configuration."""
    return {
        "source_id": "test-csv-string",
        "source_type": "string",
        "data": "id,value,description\n1,100,First\n2,200,Second\n3,300,Third",
        "use_cloud_processing": False,
    }


@pytest.fixture
def sample_excel_config():
    """Fixture providing sample Excel adapter configuration."""
    return {
        "source_id": "test-excel-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.xlsx",
        "sheet_name": "Products",
        "use_cloud_processing": False,
    }
