"""
Configuration management for the ASUS Router Exporter.

Supports:
- YAML configuration files
- Environment variable substitution (${VAR:default})
- Dot notation access (config.get('collectors.cpu.enabled'))
- Default configuration fallback
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError

# Try to import yaml, but make it optional
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class Config:
    """
    Configuration manager with environment variable substitution.

    Example:
        config = Config.load('config.yaml')
        port = config.get('exporter.port', 8000)
        cpu_enabled = config.get('collectors.cpu.enabled', True)
    """

    # Pattern for environment variable substitution: ${VAR} or ${VAR:default}
    ENV_VAR_PATTERN = re.compile(r'\$\{([^:}]+)(?::([^}]*))?\}')

    def __init__(self, data: dict[str, Any]):
        """
        Initialize configuration.

        Args:
            data: Configuration dictionary
        """
        self._data = data
        self._resolve_env_vars(self._data)

    @classmethod
    def load(cls, config_path: str | None = None) -> Config:
        """
        Load configuration from file or environment.

        Args:
            config_path: Path to YAML configuration file (optional)

        Returns:
            Config instance
        """
        data: dict[str, Any] = {}

        if config_path:
            path = Path(config_path)
            if path.exists():
                if not YAML_AVAILABLE:
                    raise ConfigurationError(
                        "PyYAML is required to load YAML config files. "
                        "Install it with: pip install pyyaml"
                    )
                try:
                    with open(path) as f:
                        data = yaml.safe_load(f) or {}
                except yaml.YAMLError as e:
                    raise ConfigurationError(f"Invalid YAML in {path}: {e}") from e
                except OSError as e:
                    raise ConfigurationError(f"Failed to read config from {path}: {e}") from e

        # Merge with defaults (defaults take lower priority)
        merged = cls._deep_merge(cls._default_config(), data)
        return cls(merged)

    @classmethod
    def from_env(cls) -> Config:
        """
        Create configuration from environment variables only.

        Returns:
            Config instance with default configuration
        """
        return cls(cls._default_config())

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'collectors.cpu.enabled')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value: Any = self._data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'router.host')
            value: Value to set
        """
        keys = key.split('.')
        data = self._data

        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]

        data[keys[-1]] = value

    def get_collector_config(self, collector_name: str) -> dict[str, Any]:
        """
        Get collector-specific configuration.

        Args:
            collector_name: Name of the collector

        Returns:
            Dictionary with collector configuration
        """
        result = self.get(f"collectors.{collector_name}", {})
        return result if isinstance(result, dict) else {}

    def is_collector_enabled(self, collector_name: str) -> bool:
        """
        Check if a collector is enabled.

        Args:
            collector_name: Name of the collector

        Returns:
            True if collector is enabled
        """
        return bool(self.get(f"collectors.{collector_name}.enabled", True))

    @staticmethod
    def _default_config() -> dict[str, Any]:
        """Get default configuration with environment variable fallbacks."""
        return {
            "router": {
                "host": os.getenv("ASUS_ROUTER_HOST", "192.168.1.1"),
                "auth": os.getenv("ASUS_ROUTER_AUTH", ""),
                "timeout": int(os.getenv("ASUS_ROUTER_TIMEOUT", "10")),
            },
            "exporter": {
                "port": int(os.getenv("ASUS_METRICS_PORT", "8000")),
                "scrape_interval": int(os.getenv("ASUS_SCRAPE_INTERVAL", "30")),
                "log_level": os.getenv("ASUS_LOG_LEVEL", "INFO"),
            },
            "error_handling": {
                "retry": {
                    "enabled": True,
                    "max_attempts": 3,
                    "backoff_factor": 2.0,
                    "max_delay": 30.0,
                },
                "circuit_breaker": {
                    "enabled": True,
                    "failure_threshold": 5,
                    "recovery_timeout": 60.0,
                    "half_open_max_calls": 3,
                },
            },
            "collectors": {
                "cpu": {"enabled": True, "track_per_core": True},
                "memory": {"enabled": True},
                "temperature": {"enabled": True},
                "network": {"enabled": True},
                "wan": {"enabled": True},
                "wireless": {"enabled": True},
                "ports": {"enabled": True},
                "clients": {"enabled": True, "max_clients": 100},
                "system": {"enabled": True},
            },
            "logging": {
                "level": os.getenv("ASUS_LOG_LEVEL", "INFO"),
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "mask_sensitive": True,
            },
        }

    def _resolve_env_vars(self, data: Any) -> Any:
        """
        Recursively resolve environment variables in configuration.

        Args:
            data: Configuration data (dict, list, or value)

        Returns:
            Data with environment variables resolved
        """
        if isinstance(data, dict):
            for key, value in data.items():
                data[key] = self._resolve_env_vars(value)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                data[i] = self._resolve_env_vars(item)
        elif isinstance(data, str):
            data = self._substitute_env_vars(data)

        return data

    def _substitute_env_vars(self, value: str) -> str:
        """
        Substitute environment variables in a string.

        Supports: ${VAR} and ${VAR:default}

        Args:
            value: String with potential env var references

        Returns:
            String with env vars substituted
        """
        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.getenv(var_name)
            if env_value is not None:
                return env_value
            return default if default is not None else ""

        return self.ENV_VAR_PATTERN.sub(replacer, value)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """
        Deep merge two dictionaries, with override taking precedence.

        Args:
            base: Base dictionary
            override: Override dictionary

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def to_dict(self) -> dict[str, Any]:
        """
        Get configuration as dictionary.

        Returns:
            Configuration dictionary
        """
        return self._data.copy()

    def __repr__(self) -> str:
        return f"Config({list(self._data.keys())})"
