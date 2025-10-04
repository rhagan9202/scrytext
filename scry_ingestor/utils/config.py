"""Configuration loader for YAML files with environment variable overrides."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError as PydanticValidationError

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
        with open(config_path, "r") as f:
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
