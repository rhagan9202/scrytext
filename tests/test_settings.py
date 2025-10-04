"""Tests for global configuration settings powered by Pydantic."""

from pathlib import Path

import pytest

from scry_ingestor.utils.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure global settings cache is cleared before and after each test."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_global_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default settings should reflect development-friendly values."""

    monkeypatch.delenv("SCRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SCRY_LOG_LEVEL", raising=False)
    monkeypatch.delenv("SCRY_AWS__REGION", raising=False)

    settings = get_settings()

    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.aws.region is None
    assert settings.config_dir == Path("config")
    assert settings.fixtures_dir == Path("tests/fixtures")


def test_global_settings_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Environment variables should override default configuration values."""

    monkeypatch.setenv("SCRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SCRY_LOG_LEVEL", "debug")
    monkeypatch.setenv("SCRY_AWS__REGION", "us-west-2")
    monkeypatch.setenv("SCRY_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("SCRY_FIXTURES_DIR", str(tmp_path / "fixtures"))

    settings = get_settings()

    assert settings.environment == "production"
    assert settings.log_level == "DEBUG"
    assert settings.aws.region == "us-west-2"
    assert settings.config_dir == (tmp_path / "config")
    assert settings.fixtures_dir == (tmp_path / "fixtures")
