"""Pytest configuration - no path manipulation, rely on proper package installation."""
import pytest


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
