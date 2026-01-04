"""
Configuration management for the ASUS Router Exporter.

Supports:
- YAML configuration files
- Environment variable substitution (${VAR:default})
- Dot notation access (config.get('collectors.cpu.enabled'))
- Default configuration fallback
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)

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
        ASUS_ROUTER_REAUTH_INTERVAL: Proactive re-auth interval in seconds (default: 0 = disabled)

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

    def __init__(self, data: dict[str, Any], *, validate: bool = True):
        """
        Initialize configuration.

        Args:
            data: Configuration dictionary
            validate: If True, validate configuration values (default: True)

        Raises:
            ConfigurationError: If validation is enabled and config values are invalid
        """
        self._data = data
        self._resolve_env_vars(self._data)
        if validate:
            self._validate()

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
            logger.warning(
                "Invalid integer value for %s: %r, using default: %d",
                name,
                value,
                default,
            )
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
            logger.warning(
                "Invalid float value for %s: %r, using default: %s",
                name,
                value,
                default,
            )
            return default

    @classmethod
    def _default_config(cls) -> dict[str, Any]:
        """Get default configuration with environment variable fallbacks."""
        return {
            "router": {
                "host": os.getenv("ASUS_ROUTER_HOST", "192.168.1.1"),
                "auth": os.getenv("ASUS_ROUTER_AUTH", ""),
                "timeout": cls._env_int("ASUS_ROUTER_TIMEOUT", 10),
                "reauth_interval": cls._env_int("ASUS_ROUTER_REAUTH_INTERVAL", 0),
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
            # Design Note: When an env var is unset and has no default, we return empty
            # string rather than raising an error. This is intentional because:
            # 1. Some config fields are optional and empty string is valid
            # 2. Required fields (like router.host/auth) will fail with clear errors
            #    when actually used (e.g., "Cannot connect to empty host")
            # 3. Raising here would break config loading for partially-filled configs
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

    def _validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ConfigurationError: If any configuration value is invalid
        """
        errors: list[str] = []

        # Validate port (1-65535)
        # Note: isinstance(bool, int) is True in Python, so we explicitly exclude booleans
        port = self.get("exporter.port")
        if port is not None:
            if not isinstance(port, int) or isinstance(port, bool) or port < 1 or port > 65535:
                errors.append(f"exporter.port must be an integer between 1 and 65535, got: {port}")

        # Validate timeout (positive)
        timeout = self.get("router.timeout")
        if timeout is not None:
            if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
                errors.append(f"router.timeout must be a positive number, got: {timeout}")

        # Validate reauth_interval (non-negative, 0 = disabled)
        reauth_interval = self.get("router.reauth_interval")
        if reauth_interval is not None:
            if not isinstance(reauth_interval, int) or isinstance(reauth_interval, bool) or reauth_interval < 0:
                errors.append(f"router.reauth_interval must be a non-negative integer, got: {reauth_interval}")

        # Validate scrape_interval (positive)
        scrape_interval = self.get("exporter.scrape_interval")
        if scrape_interval is not None:
            if (
                not isinstance(scrape_interval, (int, float))
                or isinstance(scrape_interval, bool)
                or scrape_interval <= 0
            ):
                errors.append(f"exporter.scrape_interval must be a positive number, got: {scrape_interval}")

        # Validate retry settings
        retry = self.get("error_handling.retry", {})
        if not isinstance(retry, dict):
            errors.append(f"error_handling.retry must be a dictionary, got: {type(retry).__name__}")
        elif retry:
            max_attempts = retry.get("max_attempts")
            if max_attempts is not None:
                if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
                    errors.append(f"error_handling.retry.max_attempts must be a positive integer, got: {max_attempts}")

            backoff_factor = retry.get("backoff_factor")
            if backoff_factor is not None:
                if (
                    not isinstance(backoff_factor, (int, float))
                    or isinstance(backoff_factor, bool)
                    or backoff_factor <= 0
                ):
                    errors.append(
                        f"error_handling.retry.backoff_factor must be a positive number, got: {backoff_factor}"
                    )

            max_delay = retry.get("max_delay")
            if max_delay is not None:
                if not isinstance(max_delay, (int, float)) or isinstance(max_delay, bool) or max_delay <= 0:
                    errors.append(f"error_handling.retry.max_delay must be a positive number, got: {max_delay}")

        # Validate circuit breaker settings
        circuit = self.get("error_handling.circuit_breaker", {})
        if not isinstance(circuit, dict):
            errors.append(f"error_handling.circuit_breaker must be a dictionary, got: {type(circuit).__name__}")
        elif circuit:
            failure_threshold = circuit.get("failure_threshold")
            if failure_threshold is not None:
                if (
                    not isinstance(failure_threshold, int)
                    or isinstance(failure_threshold, bool)
                    or failure_threshold < 1
                ):
                    errors.append(
                        f"error_handling.circuit_breaker.failure_threshold must be a positive integer, "
                        f"got: {failure_threshold}"
                    )

            recovery_timeout = circuit.get("recovery_timeout")
            if recovery_timeout is not None:
                if (
                    not isinstance(recovery_timeout, (int, float))
                    or isinstance(recovery_timeout, bool)
                    or recovery_timeout <= 0
                ):
                    errors.append(
                        f"error_handling.circuit_breaker.recovery_timeout must be a positive number, "
                        f"got: {recovery_timeout}"
                    )

            half_open_max_calls = circuit.get("half_open_max_calls")
            if half_open_max_calls is not None:
                if (
                    not isinstance(half_open_max_calls, int)
                    or isinstance(half_open_max_calls, bool)
                    or half_open_max_calls < 1
                ):
                    errors.append(
                        f"error_handling.circuit_breaker.half_open_max_calls must be a positive integer, "
                        f"got: {half_open_max_calls}"
                    )

        if errors:
            raise ConfigurationError("Invalid configuration:\n  - " + "\n  - ".join(errors))
