"""Configuration loader and settings helpers for Scry_Ingestor."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..exceptions import ConfigurationError


def load_yaml_config(config_path: str | Path) -> dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Configuration dictionary

    Raises:
        ConfigurationError: If file not found or invalid YAML
    """
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except FileNotFoundError:
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {e}")


def apply_env_overrides(config: dict[str, Any], prefix: str = "SCRY_") -> dict[str, Any]:
    """
    Override configuration values with environment variables.

    Environment variables should be prefixed (default: SCRY_) and use __ for nesting.
    Example: SCRY_AWS__REGION overrides config['aws']['region']

    Args:
        config: Base configuration dictionary
        prefix: Environment variable prefix

    Returns:
        Configuration with environment overrides applied
    """
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue

        # Remove prefix and split by __
        config_key = key[len(prefix) :].lower()
        keys = config_key.split("__")

        # Navigate/create nested structure
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set the value
        current[keys[-1]] = value

    return config


def validate_config(config: dict[str, Any], model: type[BaseModel]) -> BaseModel:
    """
    Validate configuration against Pydantic model.

    Args:
        config: Configuration dictionary
        model: Pydantic model class for validation

    Returns:
        Validated configuration model instance

    Raises:
        ConfigurationError: If validation fails
    """
    try:
        return model(**config)
    except PydanticValidationError as e:
        raise ConfigurationError(f"Configuration validation failed: {e}")


class AWSSettings(BaseModel):
    """AWS-specific configuration options derived from global settings."""

    model_config = ConfigDict(extra="forbid")

    region: str | None = None


class GlobalSettings(BaseSettings):
    """Global application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SCRY_",
        env_nested_delimiter="__",
        env_file=(".env", ".env.local", ".env.docker"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    redis_url: str | None = None
    database_url: str | None = None
    config_dir: Path = Path("config")
    fixtures_dir: Path = Path("tests/fixtures")
    aws: AWSSettings = AWSSettings()
    api_keys: list[str] = Field(default_factory=list)
    kafka_bootstrap_servers: str | None = None
    kafka_topic: str = "scry.ingestion.complete"
    celery_failure_threshold: int = Field(default=5, ge=1)
    celery_failure_window_seconds: int = Field(default=300, ge=1)
    celery_circuit_reset_seconds: int = Field(default=600, ge=1)
    celery_retry_backoff_seconds: float = Field(default=30.0, gt=0)
    celery_retry_max_backoff_seconds: float = Field(default=300.0, gt=0)
    celery_max_retries: int = Field(default=3, ge=0)

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """Ensure log level values are uppercase for logging config."""

        return value.upper()

    @field_validator("api_keys", mode="before")
    @classmethod
    def _parse_api_keys(cls, value: Any) -> list[str]:
        """Support comma-separated strings or iterables for API key configuration."""

        if value is None:
            return []
        if isinstance(value, str):
            keys = [item.strip() for item in value.split(",")]
            return [key for key in keys if key]
        if isinstance(value, list | tuple | set):
            return [str(item) for item in value if str(item).strip()]
        raise ValueError("api_keys must be a comma-separated string or iterable of strings")

    @field_validator("config_dir", "fixtures_dir", mode="before")
    @classmethod
    def _expand_paths(cls, value: Any) -> Any:
        """Allow string paths and expand user markers."""

        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            return Path(value).expanduser()
        return value



def ensure_runtime_configuration(settings: GlobalSettings) -> None:
    """Raise :class:`ConfigurationError` when critical secrets are missing."""

    missing: list[str] = []
    if not settings.database_url:
        missing.append("SCRY_DATABASE_URL")
    if not settings.api_keys:
        missing.append("SCRY_API_KEYS")

    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            "Missing required environment variables: "
            f"{joined}. Configure them via a .env file or deployment secrets."
        )


@lru_cache(maxsize=1)
def get_settings() -> GlobalSettings:
    """Return a cached instance of :class:`GlobalSettings`."""

    return GlobalSettings()
