"""Shared Kafka configuration helpers."""

from __future__ import annotations

from ..utils.config import GlobalSettings


def build_common_kafka_config(settings: GlobalSettings) -> dict[str, str]:
    """Build base Kafka client configuration shared by producers and consumers."""

    config: dict[str, str] = {}

    if settings.kafka_bootstrap_servers:
        config["bootstrap.servers"] = settings.kafka_bootstrap_servers

    config["client.id"] = settings.kafka_client_id

    if settings.kafka_security_protocol:
        config["security.protocol"] = settings.kafka_security_protocol

    if settings.kafka_sasl_mechanism:
        config["sasl.mechanism"] = settings.kafka_sasl_mechanism

    if settings.kafka_sasl_username:
        config["sasl.username"] = settings.kafka_sasl_username

    if settings.kafka_sasl_password:
        config["sasl.password"] = settings.kafka_sasl_password

    return config


def build_producer_config(settings: GlobalSettings) -> dict[str, str]:
    """Return Kafka producer configuration."""

    config = build_common_kafka_config(settings)

    # Enable reliability-focused defaults
    config.setdefault("enable.idempotence", "true")
    config.setdefault("acks", "all")
    config.setdefault("compression.type", "snappy")
    config.setdefault("linger.ms", "50")
    config.setdefault("retries", "3")

    return config


def build_consumer_config(settings: GlobalSettings, group_id: str) -> dict[str, str]:
    """Return Kafka consumer configuration."""

    config = build_common_kafka_config(settings)
    config["group.id"] = group_id
    config.setdefault("auto.offset.reset", "earliest")
    config.setdefault("enable.auto.commit", "false")

    return config


def build_schema_registry_config(settings: GlobalSettings) -> dict[str, str] | None:
    """Return schema registry client configuration if configured."""

    if not settings.kafka_schema_registry_url:
        return None

    config: dict[str, str] = {"url": settings.kafka_schema_registry_url}

    if settings.kafka_schema_registry_api_key and settings.kafka_schema_registry_api_secret:
        config["basic.auth.user.info"] = (
            f"{settings.kafka_schema_registry_api_key}:{settings.kafka_schema_registry_api_secret}"
        )

    return config
