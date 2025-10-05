"""Tests for global configuration settings powered by Pydantic."""

import json
import os
from pathlib import Path

import pytest
import yaml

from scry_ingestor.utils.config import (
    ConfigurationError,
    ensure_runtime_configuration,
    get_service_configuration,
    get_settings,
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure global settings cache is cleared before and after each test."""

    get_settings(reload=True)
    try:
        get_service_configuration(reload=True)
    except ConfigurationError:
        pass
    yield
    get_settings(reload=True)
    try:
        get_service_configuration(reload=True)
    except ConfigurationError:
        pass


def test_global_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default settings should reflect development-friendly values."""

    monkeypatch.delenv("SCRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SCRY_LOG_LEVEL", raising=False)
    monkeypatch.delenv("SCRY_AWS__REGION", raising=False)

    settings = get_settings(reload=True)

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

    settings = get_settings(reload=True)

    assert settings.environment == "production"
    assert settings.log_level == "DEBUG"
    assert settings.aws.region == "us-west-2"
    assert settings.config_dir == (tmp_path / "config")
    assert settings.fixtures_dir == (tmp_path / "fixtures")


def test_get_service_configuration_merges_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Service configuration should merge base and environment overrides."""

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    base_config = {
        "version": 1,
        "required_env": ["SCRY_DATABASE_URL", "SCRY_API_KEYS"],
        "messaging": {
            "kafka": {
                "consumer_group": "base-consumer",
                "required_env": ["SCRY_KAFKA_BOOTSTRAP_SERVERS"],
            }
        },
    }

    prod_override = {
        "required_env": ["SCRY_REDIS_URL"],
        "messaging": {
            "kafka": {
                "consumer_group": "prod-consumer",
                "required_env": ["SCRY_KAFKA_SCHEMA_REGISTRY_URL"],
            }
        },
    }

    (config_dir / "settings.base.yaml").write_text(yaml.safe_dump(base_config))
    (config_dir / "settings.production.yaml").write_text(yaml.safe_dump(prod_override))

    monkeypatch.setenv("SCRY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SCRY_ENVIRONMENT", "production")
    monkeypatch.delenv("SCRY_CONFIG_PROFILE", raising=False)

    settings = get_settings(reload=True)
    service_config = get_service_configuration(settings=settings, reload=True)

    assert service_config.environment == "production"
    assert service_config.messaging.kafka.consumer_group == "prod-consumer"
    assert "SCRY_KAFKA_SCHEMA_REGISTRY_URL" in service_config.messaging.kafka.required_env
    assert "SCRY_REDIS_URL" in service_config.required_env


def test_ensure_runtime_configuration_loads_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Secrets Manager integration should populate missing environment variables."""

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    base_config = {
        "version": 1,
        "required_env": ["SCRY_DATABASE_URL", "SCRY_API_KEYS"],
        "messaging": {
            "kafka": {
                "required_env": ["SCRY_KAFKA_BOOTSTRAP_SERVERS"],
            }
        },
    }

    prod_override = {
        "required_env": ["SCRY_REDIS_URL"],
        "messaging": {
            "kafka": {
                "required_env": [
                    "SCRY_KAFKA_SCHEMA_REGISTRY_URL",
                    "SCRY_KAFKA_SASL_USERNAME",
                    "SCRY_KAFKA_SASL_PASSWORD",
                ],
            }
        },
        "secrets_manager": {
            "enabled": True,
            "secret_name": "scry-test/production",
            "region": "us-east-1",
            "overwrite_env": True,
        },
    }

    (config_dir / "settings.base.yaml").write_text(yaml.safe_dump(base_config))
    (config_dir / "settings.production.yaml").write_text(yaml.safe_dump(prod_override))

    secret_payload = {
        "SCRY_DATABASE_URL": "postgresql://user:pass@localhost:5432/scry",
        "SCRY_API_KEYS": ["key-one", "key-two"],
        "SCRY_KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "SCRY_KAFKA_SCHEMA_REGISTRY_URL": "http://localhost:8081",
        "SCRY_KAFKA_SASL_USERNAME": "user",
        "SCRY_KAFKA_SASL_PASSWORD": "password",
        "SCRY_REDIS_URL": "redis://localhost:6379/0",
    }

    class _FakeSecretsClient:
        def get_secret_value(self, **kwargs):  # pragma: no cover - test double
            assert kwargs.get("SecretId") == "scry-test/production"
            return {"SecretString": json.dumps(secret_payload)}


    class _FakeSession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def client(self, service_name: str, endpoint_url: str | None = None):
            assert service_name == "secretsmanager"
            return _FakeSecretsClient()

    monkeypatch.setattr("scry_ingestor.utils.config.Session", _FakeSession)

    for env_var in secret_payload:
        monkeypatch.delenv(env_var, raising=False)

    monkeypatch.setenv("SCRY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SCRY_ENVIRONMENT", "production")

    settings = get_settings(reload=True)
    updated_settings = ensure_runtime_configuration(settings)

    assert os.environ["SCRY_DATABASE_URL"] == secret_payload["SCRY_DATABASE_URL"]
    assert os.environ["SCRY_API_KEYS"] == json.dumps(secret_payload["SCRY_API_KEYS"])
    assert updated_settings.database_url == secret_payload["SCRY_DATABASE_URL"]
    assert updated_settings.api_keys == ["key-one", "key-two"]
