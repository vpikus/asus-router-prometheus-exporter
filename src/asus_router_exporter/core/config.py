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

    All configuration options can be set via environment variables:

    Router:
        ASUS_ROUTER_HOST: Router IP address or hostname (default: 192.168.1.1)
        ASUS_ROUTER_AUTH: Authentication as username:password (required)
        ASUS_ROUTER_TIMEOUT: Request timeout in seconds (default: 10)

    Exporter:
        ASUS_METRICS_PORT: Metrics HTTP port (default: 8000)
        ASUS_SCRAPE_INTERVAL: Collection interval in seconds (default: 30)
        ASUS_LOG_LEVEL: Log level DEBUG/INFO/WARNING/ERROR (default: INFO)

    Error Handling:
        ASUS_RETRY_ENABLED: Enable retry mechanism (default: true)
        ASUS_RETRY_MAX_ATTEMPTS: Max retry attempts (default: 3)
        ASUS_RETRY_BACKOFF_FACTOR: Exponential backoff factor (default: 2.0)
        ASUS_CIRCUIT_BREAKER_ENABLED: Enable circuit breaker (default: true)
        ASUS_CIRCUIT_BREAKER_FAILURE_THRESHOLD: Failures before open (default: 5)
        ASUS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: Recovery timeout in seconds (default: 60.0)

    Collectors (all default to true):
        ASUS_COLLECTOR_CPU_ENABLED: Enable CPU metrics
        ASUS_COLLECTOR_MEMORY_ENABLED: Enable memory metrics
        ASUS_COLLECTOR_TEMPERATURE_ENABLED: Enable temperature metrics
        ASUS_COLLECTOR_NETWORK_ENABLED: Enable network metrics
        ASUS_COLLECTOR_WAN_ENABLED: Enable WAN metrics
        ASUS_COLLECTOR_WIRELESS_ENABLED: Enable wireless metrics
        ASUS_COLLECTOR_PORTS_ENABLED: Enable port metrics
        ASUS_COLLECTOR_CLIENTS_ENABLED: Enable client metrics
        ASUS_COLLECTOR_SYSTEM_ENABLED: Enable system/router info metrics

    Example:
        config = Config.load('config.yaml')
        port = config.get('exporter.port', 8000)
        cpu_enabled = config.get('collectors.cpu.enabled', True)
    """

    # Pattern for environment variable substitution: ${VAR} or ${VAR:default}
    ENV_VAR_PATTERN = re.compile(r"\$\{([^:}]+)(?::([^}]*))?\}")

    def __init__(self, data: dict[str, Any]):
        """
        Initialize configuration.

        Design Note on Validation:
            This config module intentionally does not validate bounds (e.g., port
            ranges, timeout positivity). This is by design because:
            1. External validation occurs at use time (OS rejects invalid ports
               when binding, requests library handles invalid timeouts)
            2. Components that consume config values can validate in context
            3. Adding bounds validation here would duplicate logic and add
               complexity without meaningful safety benefits
            4. Invalid values will fail fast with clear error messages from the
               actual consumer (e.g., "Cannot bind to port -1")

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
                        "PyYAML is required to load YAML config files. Install it with: pip install pyyaml"
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
        keys = key.split(".")
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
        keys = key.split(".")
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
    def _env_bool(name: str, default: bool) -> bool:
        """
        Get boolean value from environment variable.

        Truthy values: 'true', '1', 'yes', 'on' (case-insensitive)
        Falsy values: 'false', '0', 'no', 'off' (case-insensitive)

        Args:
            name: Environment variable name
            default: Default value if not set

        Returns:
            Boolean value
        """
        value = os.getenv(name)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        """Get integer value from environment variable."""
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        """Get float value from environment variable."""
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @classmethod
    def _default_config(cls) -> dict[str, Any]:
        """Get default configuration with environment variable fallbacks."""
        return {
            "router": {
                "host": os.getenv("ASUS_ROUTER_HOST", "192.168.1.1"),
                "auth": os.getenv("ASUS_ROUTER_AUTH", ""),
                "timeout": cls._env_int("ASUS_ROUTER_TIMEOUT", 10),
            },
            "exporter": {
                "port": cls._env_int("ASUS_METRICS_PORT", 8000),
                "scrape_interval": cls._env_int("ASUS_SCRAPE_INTERVAL", 30),
                "log_level": os.getenv("ASUS_LOG_LEVEL", "INFO"),
            },
            "error_handling": {
                "retry": {
                    "enabled": cls._env_bool("ASUS_RETRY_ENABLED", True),
                    "max_attempts": cls._env_int("ASUS_RETRY_MAX_ATTEMPTS", 3),
                    "backoff_factor": cls._env_float("ASUS_RETRY_BACKOFF_FACTOR", 2.0),
                    "max_delay": cls._env_float("ASUS_RETRY_MAX_DELAY", 30.0),
                },
                "circuit_breaker": {
                    "enabled": cls._env_bool("ASUS_CIRCUIT_BREAKER_ENABLED", True),
                    "failure_threshold": cls._env_int("ASUS_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5),
                    "recovery_timeout": cls._env_float("ASUS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 60.0),
                    "half_open_max_calls": cls._env_int("ASUS_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS", 3),
                },
            },
            "collectors": {
                "cpu": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_CPU_ENABLED", True),
                    "track_per_core": cls._env_bool("ASUS_COLLECTOR_CPU_TRACK_PER_CORE", True),
                },
                "memory": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_MEMORY_ENABLED", True),
                },
                "temperature": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_TEMPERATURE_ENABLED", True),
                },
                "network": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_NETWORK_ENABLED", True),
                },
                "wan": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_WAN_ENABLED", True),
                },
                "wireless": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_WIRELESS_ENABLED", True),
                },
                "ports": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_PORTS_ENABLED", True),
                },
                "clients": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_CLIENTS_ENABLED", True),
                    "max_clients": cls._env_int("ASUS_COLLECTOR_CLIENTS_MAX", 100),
                },
                "system": {
                    "enabled": cls._env_bool("ASUS_COLLECTOR_SYSTEM_ENABLED", True),
                },
            },
            "logging": {
                "level": os.getenv("ASUS_LOG_LEVEL", "INFO"),
                "format": os.getenv("ASUS_LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
                "mask_sensitive": cls._env_bool("ASUS_LOG_MASK_SENSITIVE", True),
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
