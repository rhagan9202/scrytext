"""Configuration loader and settings helpers for Scry_Ingestor."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
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
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    redis_url: str | None = None
    config_dir: Path = Path("config")
    fixtures_dir: Path = Path("tests/fixtures")
    aws: AWSSettings = AWSSettings()

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """Ensure log level values are uppercase for logging config."""

        return value.upper()

    @field_validator("config_dir", "fixtures_dir", mode="before")
    @classmethod
    def _expand_paths(cls, value: Any) -> Any:
        """Allow string paths and expand user markers."""

        if isinstance(value, Path):
            return value
        if isinstance(value, str):
            return Path(value).expanduser()
        return value


@lru_cache(maxsize=1)
def get_settings() -> GlobalSettings:
    """Return a cached instance of :class:`GlobalSettings`."""

    return GlobalSettings()
