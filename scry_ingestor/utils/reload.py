"""Configuration reload utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..utils.config import get_settings
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class ConfigReloader:
    """
    Manages hot-reloading of configuration without service restart.

    Supports reloading adapter configurations, feature flags, and operational
    parameters that don't require service restart.
    """

    def __init__(self) -> None:
        """Initialize configuration reloader."""
        self._config_cache: dict[str, dict[str, Any]] = {}
        settings = get_settings()
        self._config_dir = Path(settings.config_dir)

    def reload_adapter_configs(self) -> dict[str, Any]:
        """
        Reload all adapter configuration files.

        Returns:
            Dictionary mapping adapter names to their configurations
        """
        adapter_configs: dict[str, Any] = {}

        adapter_files = [
            "pdf_adapter.yaml",
            "word_adapter.yaml",
            "json_adapter.yaml",
            "csv_adapter.yaml",
            "excel_adapter.yaml",
            "rest_adapter.yaml",
            "soup_adapter.yaml",
        ]

        for filename in adapter_files:
            config_path = self._config_dir / filename
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = yaml.safe_load(f)
                    adapter_name = filename.replace("_adapter.yaml", "")
                    adapter_configs[adapter_name] = config
                    logger.info(f"Reloaded adapter config: {adapter_name}")
                except Exception as e:
                    logger.error(f"Failed to reload {filename}: {e}")
            else:
                logger.warning(f"Adapter config not found: {config_path}")

        self._config_cache["adapters"] = adapter_configs
        return adapter_configs

    def reload_settings(self) -> dict[str, Any]:
        """
        Reload base settings configuration.

        Note: Only reloads hot-swappable settings. Some settings like database
        URLs require service restart.

        Returns:
            Dictionary of reloadable settings
        """
        settings = get_settings()
        reloadable_settings = {
            "environment": settings.environment,
            "log_level": settings.log_level,
            "redis_url": settings.redis_url,
        }

        # Reload environment-specific settings
        env_file = self._config_dir / f"settings.{settings.environment}.yaml"
        if env_file.exists():
            try:
                with open(env_file) as f:
                    env_config = yaml.safe_load(f)
                reloadable_settings.update(env_config)
                logger.info(f"Reloaded environment settings: {settings.environment}")
            except Exception as e:
                logger.error(f"Failed to reload environment settings: {e}")

        self._config_cache["settings"] = reloadable_settings
        return reloadable_settings

    def get_adapter_config(self, adapter_name: str) -> dict[str, Any] | None:
        """
        Get cached adapter configuration.

        Args:
            adapter_name: Name of the adapter (e.g., 'pdf', 'word')

        Returns:
            Adapter configuration dictionary or None if not found
        """
        adapters = self._config_cache.get("adapters", {})
        return adapters.get(adapter_name)

    def reload_all(self) -> dict[str, Any]:
        """
        Reload all hot-swappable configurations.

        Returns:
            Dictionary with all reloaded configurations
        """
        logger.info("Starting full configuration reload...")

        result = {
            "adapters": self.reload_adapter_configs(),
            "settings": self.reload_settings(),
            "status": "success",
        }

        logger.info("Configuration reload complete")
        return result


# Global config reloader instance
_config_reloader: ConfigReloader | None = None


def get_config_reloader() -> ConfigReloader:
    """Get or create global config reloader instance."""
    global _config_reloader
    if _config_reloader is None:
        _config_reloader = ConfigReloader()
    return _config_reloader


async def reload_configuration() -> dict[str, Any]:
    """
    Async wrapper for configuration reload.

    Can be used as SIGHUP handler or called from API endpoint.

    Returns:
        Dictionary with reload results
    """
    reloader = get_config_reloader()
    return reloader.reload_all()
