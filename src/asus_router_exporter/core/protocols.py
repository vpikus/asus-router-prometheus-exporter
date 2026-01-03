"""
Core protocols (interfaces) for the ASUS Router Exporter.

These protocols define the contracts that components must implement,
enabling dependency injection and testability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass


class RouterClientProtocol(Protocol):
    """Protocol for router client interface."""

    def clear_cache(self) -> None:
        """Clear any cached data.

        Should be called at the start of each collection cycle to ensure
        fresh data is fetched from the router.
        """
        ...

    def get_info(self) -> Any:
        """Get router information."""
        ...

    def get_core_temp(self) -> Any:
        """Get CPU temperature."""
        ...

    def get_cpu_usage(self) -> list[Any]:
        """Get CPU usage for all cores."""
        ...

    def get_memory_usage(self) -> Any:
        """Get memory usage statistics."""
        ...

    def get_netdev(self) -> Any:
        """Get network device statistics."""
        ...

    def get_network_wan_info(self) -> Any:
        """Get WAN connection information."""
        ...

    def get_wireless_info(self) -> Any:
        """Get wireless information."""
        ...

    def get_clients(self) -> list[Any]:
        """Get connected clients list."""
        ...


class MetricCollectorProtocol(Protocol):
    """Protocol for metric collectors."""

    @property
    def name(self) -> str:
        """Unique collector name (e.g., 'cpu', 'memory')."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether this collector is enabled."""
        ...

    def collect(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """
        Collect metrics from router.

        Args:
            router_client: Client for router API calls.
            router_info: Router information containing product_id and other details.
        """
        ...

    def cleanup(self) -> None:
        """Clean up collector resources and clear metrics."""
        ...


class ConfigProviderProtocol(Protocol):
    """Protocol for configuration providers."""

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Args:
            key: Configuration key (e.g., 'collectors.cpu.enabled')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        ...

    def get_collector_config(self, collector_name: str) -> dict[str, Any]:
        """
        Get collector-specific configuration.

        Args:
            collector_name: Name of the collector

        Returns:
            Dictionary with collector configuration
        """
        ...


class ErrorHandlerProtocol(Protocol):
    """Protocol for error handling strategies."""

    def execute(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Execute function with error handling.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If all retry attempts fail or circuit is open
        """
        ...
