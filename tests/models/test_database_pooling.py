"""Tests for database connection pooling configuration."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from scry_ingestor.models import base as models_base
from scry_ingestor.utils.config import get_settings


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    """Ensure cached settings and engine state are reset around each test."""

    get_settings(reload=True)
    models_base.reset_engine()
    yield
    get_settings(reload=True)
    models_base.reset_engine()


def test_create_engine_applies_pool_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-SQLite URLs should honour pool configuration from settings."""

    monkeypatch.setenv("SCRY_DATABASE_URL", "postgresql://user:pass@localhost:5432/scry")
    monkeypatch.setenv("SCRY_DATABASE__POOL_SIZE", "7")
    monkeypatch.setenv("SCRY_DATABASE__MAX_OVERFLOW", "3")
    monkeypatch.setenv("SCRY_DATABASE__TIMEOUT", "15.5")
    monkeypatch.setenv("SCRY_DATABASE__RECYCLE_SECONDS", "1200")
    monkeypatch.setenv("SCRY_DATABASE__PRE_PING", "true")

    get_settings(reload=True)

    captured: dict[str, Any] = {}
    stub_engine = object()

    def _fake_create_engine(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return stub_engine

    monkeypatch.setattr(models_base, "create_engine", _fake_create_engine)

    engine = models_base._create_engine()

    assert engine is stub_engine
    assert captured["url"].startswith("postgresql")
    assert captured["kwargs"]["pool_size"] == 7
    assert captured["kwargs"]["max_overflow"] == 3
    assert captured["kwargs"]["pool_timeout"] == pytest.approx(15.5)
    assert captured["kwargs"]["pool_pre_ping"] is True
    assert captured["kwargs"]["pool_recycle"] == 1200


def test_create_engine_skips_pool_configuration_for_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLite engines should not receive pooling kwargs beyond connect args."""

    monkeypatch.setenv("SCRY_DATABASE_URL", "sqlite:///./scry_ingestor.db")
    get_settings(reload=True)

    captured: dict[str, Any] = {}

    def _fake_create_engine(url: str, **kwargs: Any) -> Any:
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(models_base, "create_engine", _fake_create_engine)

    models_base._create_engine()

    assert captured["kwargs"]["connect_args"] == {"check_same_thread": False}
    # Ensure no pooling kwargs slipped through for SQLite
    assert "pool_size" not in captured["kwargs"]
    assert "pool_timeout" not in captured["kwargs"]
