"""Configuration loader and settings helpers for Scry_Ingestor."""

import base64
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from boto3.session import Session
from botocore.exceptions import BotoCoreError, ClientError
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


logger = logging.getLogger(__name__)


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


class DatabasePoolSettings(BaseModel):
    """Connection pooling configuration for the SQLAlchemy engine."""

    model_config = ConfigDict(extra="forbid")

    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    timeout: float = Field(default=30.0, gt=0)
    recycle_seconds: int = Field(default=1800, ge=0)
    pre_ping: bool = True


class SecretsManagerSettings(BaseModel):
    """AWS Secrets Manager integration settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    secret_name: str | None = None
    region: str | None = None
    profile: str | None = None
    endpoint_url: str | None = None
    overwrite_env: bool = False
    required_env: list[str] = Field(default_factory=list)


class KafkaConfig(BaseModel):
    """Kafka messaging configuration defaults and requirements."""

    topic: str = "scry.ingestion.complete"
    consumer_group: str = "scry-ingestor-consumer"
    require_schema_registry: bool = True
    required_env: list[str] = Field(default_factory=list)


class MessagingConfig(BaseModel):
    """Messaging configuration section for runtime validation."""

    kafka: KafkaConfig = Field(default_factory=KafkaConfig)


class ServiceConfiguration(BaseModel):
    """Validated runtime configuration merged from base and environment overrides."""

    version: int = Field(default=1, ge=1)
    environment: str = "development"
    required_env: list[str] = Field(default_factory=list)
    messaging: MessagingConfig = Field(default_factory=MessagingConfig)
    secrets_manager: SecretsManagerSettings = Field(default_factory=SecretsManagerSettings)

    @field_validator("environment")
    @classmethod
    def _normalize_environment(cls, value: str) -> str:
        return value.lower()


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
    config_profile: str | None = None
    log_level: str = "INFO"
    redis_url: str | None = None
    database_url: str | None = None
    database: DatabasePoolSettings = DatabasePoolSettings()
    config_dir: Path = Path("config")
    fixtures_dir: Path = Path("tests/fixtures")
    aws: AWSSettings = AWSSettings()
    secrets_manager: SecretsManagerSettings = SecretsManagerSettings()
    api_keys: list[str] = Field(default_factory=list)
    kafka_bootstrap_servers: str | None = None
    kafka_topic: str = "scry.ingestion.complete"
    kafka_client_id: str = "scry-ingestor"
    kafka_consumer_group: str = "scry-ingestor-consumer"
    kafka_publish_timeout_seconds: float = Field(default=5.0, gt=0)
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None
    kafka_schema_registry_url: str | None = None
    kafka_schema_registry_api_key: str | None = None
    kafka_schema_registry_api_secret: str | None = None
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

    @field_validator("kafka_security_protocol", "kafka_sasl_mechanism", mode="before")
    @classmethod
    def _normalize_kafka_values(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).upper()

    @field_validator("config_profile", mode="before")
    @classmethod
    def _normalize_config_profile(cls, value: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("config_profile must be a non-empty string if provided")
        return value.strip().lower()


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries without mutating the inputs."""

    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


@lru_cache(maxsize=8)
def _load_service_configuration_cached(config_dir: str, profile: str) -> ServiceConfiguration:
    """Load and cache the service configuration for a given profile."""

    directory = Path(config_dir)
    base_path = directory / "settings.base.yaml"
    if not base_path.exists():
        raise ConfigurationError(
            f"Missing base configuration template at '{base_path}'. "
            "Create this file to define shared defaults."
        )

    base_config = load_yaml_config(base_path)

    profile_path = directory / f"settings.{profile}.yaml"
    profile_config: dict[str, Any] = {}
    if profile_path.exists():
        profile_config = load_yaml_config(profile_path)
    else:
        logger.debug("No configuration override found for profile '%s'", profile)

    merged = _deep_merge_dicts(base_config, profile_config)
    merged.setdefault("environment", profile)

    try:
        return ServiceConfiguration.model_validate(merged)
    except PydanticValidationError as exc:  # pragma: no cover - validation details bubbled up
        raise ConfigurationError(
            "Invalid configuration template for profile "
            f"'{profile}': {exc}"
        ) from exc


def get_service_configuration(
    settings: GlobalSettings | None = None,
    *,
    reload: bool = False,
) -> ServiceConfiguration:
    """Return the merged service configuration for the active profile."""

    if settings is None:
        settings = get_settings()

    profile = settings.config_profile or settings.environment

    if reload:
        _load_service_configuration_cached.cache_clear()

    return _load_service_configuration_cached(str(settings.config_dir), profile.lower())


def _fetch_secrets_from_manager(
    *,
    secret_name: str,
    region: str | None,
    profile: str | None,
    endpoint_url: str | None,
) -> dict[str, str]:
    """Retrieve secrets from AWS Secrets Manager."""

    session_kwargs: dict[str, Any] = {}
    if region:
        session_kwargs["region_name"] = region
    if profile:
        session_kwargs["profile_name"] = profile

    session = Session(**session_kwargs)
    client = session.client("secretsmanager", endpoint_url=endpoint_url)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - dependency errors
        raise ConfigurationError(
            f"Unable to retrieve secret '{secret_name}' from AWS Secrets Manager: {exc}"
        ) from exc

    secret_string = response.get("SecretString")
    if secret_string is None:
        secret_binary = response.get("SecretBinary")
        if secret_binary is None:
            return {}
        if isinstance(secret_binary, (bytes, bytearray)):
            secret_string = base64.b64decode(secret_binary).decode("utf-8")
        else:  # pragma: no cover - defensive branch
            secret_string = str(secret_binary)

    try:
        payload = json.loads(secret_string)
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid payload
        raise ConfigurationError(
            "Secrets Manager payload must be valid JSON mapping of environment variables"
        ) from exc

    if not isinstance(payload, dict):  # pragma: no cover - invalid shape
        raise ConfigurationError(
            "Secrets Manager payload must be a JSON object of key/value pairs"
        )

    secrets: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            logger.debug("Skipping non-string secret key: %s", key)
            continue
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            try:
                secrets[key] = json.dumps(value)
            except TypeError:  # pragma: no cover - defensive branch for non-serializable types
                secrets[key] = str(value)
        else:
            secrets[key] = str(value)

    return secrets


def _inject_secrets_into_environment(secrets: dict[str, str], *, overwrite: bool) -> None:
    """Inject secrets into os.environ respecting overwrite flag."""

    if not secrets:
        return

    for key, value in secrets.items():
        env_key = key if key.isupper() else key.upper()
        if not env_key.startswith("SCRY_"):
            logger.debug("Ignoring secret '%s' because it does not use SCRY_ prefix", env_key)
            continue
        if not overwrite and env_key in os.environ:
            continue
        os.environ[env_key] = value


def load_runtime_secrets(
    settings: GlobalSettings,
    service_config: ServiceConfiguration,
) -> dict[str, str]:
    """Load secrets defined in configuration or environment and inject them."""

    secrets_cfg = settings.secrets_manager
    config_cfg = service_config.secrets_manager

    enabled = secrets_cfg.enabled or config_cfg.enabled
    if not enabled:
        return {}

    secret_name = secrets_cfg.secret_name or config_cfg.secret_name
    if not secret_name:
        raise ConfigurationError(
            "Secrets Manager integration enabled but no secret_name configured"
        )

    region = secrets_cfg.region or config_cfg.region or settings.aws.region
    profile = secrets_cfg.profile or config_cfg.profile
    endpoint_url = secrets_cfg.endpoint_url or config_cfg.endpoint_url
    overwrite = secrets_cfg.overwrite_env or config_cfg.overwrite_env

    secrets = _fetch_secrets_from_manager(
        secret_name=secret_name,
        region=region,
        profile=profile,
        endpoint_url=endpoint_url,
    )

    _inject_secrets_into_environment(secrets, overwrite=overwrite)
    return secrets


def ensure_runtime_configuration(settings: GlobalSettings | None = None) -> GlobalSettings:
    """Validate configuration templates, load secrets, and ensure required env vars."""

    settings = settings or get_settings()

    service_config = get_service_configuration(settings=settings, reload=True)

    secrets = load_runtime_secrets(settings, service_config)
    if secrets:
        logger.info("Loaded %d secrets from AWS Secrets Manager", len(secrets))
        settings = get_settings(reload=True)

    required_env: set[str] = set(service_config.required_env)
    required_env.update(service_config.messaging.kafka.required_env)
    required_env.update(service_config.secrets_manager.required_env)

    # Ensure historic requirements remain enforced even if templates change.
    required_env.update({"SCRY_DATABASE_URL", "SCRY_API_KEYS"})

    missing = sorted(var for var in required_env if not os.environ.get(var))

    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            "Missing required environment variables: "
            f"{joined}. Configure them via configuration templates, Secrets Manager, or .env files."
        )

    return settings


@lru_cache(maxsize=1)
def _get_settings_cached() -> GlobalSettings:
    return GlobalSettings()


def get_settings(*, reload: bool = False) -> GlobalSettings:
    """Return cached settings, optionally forcing a reload."""

    if reload:
        _get_settings_cached.cache_clear()
    return _get_settings_cached()
