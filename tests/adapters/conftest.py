"""Shared pytest fixtures for adapter integration tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def sample_pdf_config() -> dict[str, Any]:
    """Return configuration for the sample PDF adapter fixture."""

    return {
        "source_id": "test-pdf-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.pdf",
        "use_cloud_processing": False,
    }


@pytest.fixture
def pdf_config_with_tables(sample_pdf_config: dict[str, Any]) -> dict[str, Any]:
    """Return PDF adapter configuration with table extraction enabled."""

    config = {**sample_pdf_config}
    config.update(
        {
            "source_id": "test-pdf-tables",
            "transformation": {
                "extract_tables": True,
                "extract_metadata": True,
            },
        }
    )
    return config


@pytest.fixture
def pdf_config_with_validation(sample_pdf_config: dict[str, Any]) -> dict[str, Any]:
    """Return PDF adapter configuration with strict validation requirements."""

    config = {**sample_pdf_config}
    config.update(
        {
            "source_id": "test-pdf-strict",
            "validation": {
                "min_pages": 2,
                "min_words": 10,
                "allow_empty": False,
            },
        }
    )
    return config


@pytest.fixture
def pdf_config_layout_mode(sample_pdf_config: dict[str, Any]) -> dict[str, Any]:
    """Return PDF adapter configuration that preserves page layout during extraction."""

    config = {**sample_pdf_config}
    config.update(
        {
            "source_id": "test-pdf-layout",
            "transformation": {
                "layout_mode": True,
                "extract_metadata": True,
            },
        }
    )
    return config


@pytest.fixture
def sample_word_config() -> dict[str, Any]:
    """Return configuration for the sample Word adapter fixture."""

    return {
        "source_id": "test-word-source",
        "source_type": "file",
        "path": "tests/fixtures/sample.docx",
        "use_cloud_processing": False,
    }


@pytest.fixture
def word_config_with_validation(sample_word_config: dict[str, Any]) -> dict[str, Any]:
    """Return Word adapter configuration with strict validation rules."""

    config = {**sample_word_config}
    config.update(
        {
            "source_id": "test-word-strict",
            "validation": {
                "min_paragraphs": 3,
                "min_words": 10,
                "allow_empty": False,
            },
        }
    )
    return config


@pytest.fixture
def word_config_with_tables(sample_word_config: dict[str, Any]) -> dict[str, Any]:
    """Return Word adapter configuration with table extraction enabled."""

    config = {**sample_word_config}
    config.update(
        {
            "source_id": "test-word-tables",
            "transformation": {
                "extract_tables": True,
                "extract_metadata": True,
            },
        }
    )
    return config


@pytest.fixture
def rest_adapter_config() -> dict[str, Any]:
    """Return baseline REST adapter configuration for HTTPX transport tests."""

    return {
        "source_id": "rest-test",
        "endpoint": "https://api.example.com/data",
        "method": "GET",
        "query_params": {"limit": "10"},
        "headers": {"Accept": "application/json"},
        "validation": {"expected_statuses": [200]},
        "transformation": {"response_format": "json"},
    }


@pytest.fixture
def soup_adapter_config() -> dict[str, Any]:
    """Return baseline BeautifulSoup adapter configuration for HTML ingestion tests."""

    return {
        "source_id": "soup-test",
        "url": "https://example.com/articles",
        "validation": {"expected_statuses": [200]},
        "transformation": {
            "include_links": True,
            "include_metadata": True,
            "selectors": {
                "headlines": "article h1",
                "summaries": "article p.summary",
            },
        },
    }
