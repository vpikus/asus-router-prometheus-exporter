"""
Dependency injection container for the ASUS Router Exporter.

Manages the creation and lifecycle of all application components,
providing loose coupling and easy testability.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY, CollectorRegistry

from .config import Config
from .error_handling import CompositeErrorHandler
from .protocols import RouterClientProtocol

if TYPE_CHECKING:
    from ..collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class Container:
    """
    Dependency injection container.

    Manages the lifecycle of all application components:
    - Configuration
    - Router client
    - Error handling
    - Metric collectors
    - Prometheus registry

    Note:
        This container is designed for single-threaded use. The lazy property
        initialization (router_client, error_handler) is not thread-safe.
        The exporter runs metric collection in a single thread, and Prometheus
        client handles HTTP scrape thread-safety at its own level.

    Example:
        container = Container.from_config("config.yaml")
        container.register_collector(CPUCollector)
        container.register_collector(MemoryCollector)

        app = container.create_exporter()
        app.run()
    """

    def __init__(
        self,
        config: Config,
        registry: CollectorRegistry | None = None,
    ):
        """
        Initialize container.

        Args:
            config: Application configuration
            registry: Prometheus registry (uses default if not provided)
        """
        self._config = config
        self._registry = registry or REGISTRY
        self._router_client: RouterClientProtocol | None = None
        self._error_handler: CompositeErrorHandler | None = None
        self._collector_classes: list[type[BaseCollector]] = []
        self._collectors: list[BaseCollector] = []
        self._initialized = False

    @classmethod
    def from_config(
        cls,
        config_path: str | None = None,
        registry: CollectorRegistry | None = None,
    ) -> Container:
        """
        Create container from configuration file.

        Args:
            config_path: Path to YAML configuration file
            registry: Prometheus registry (uses default if not provided)

        Returns:
            Configured container instance
        """
        config = Config.load(config_path)
        return cls(config, registry)

    @classmethod
    def from_env(
        cls,
        registry: CollectorRegistry | None = None,
    ) -> Container:
        """
        Create container from environment variables only.

        Args:
            registry: Prometheus registry (uses default if not provided)

        Returns:
            Container configured from environment
        """
        config = Config.from_env()
        return cls(config, registry)

    @property
    def config(self) -> Config:
        """Get configuration."""
        return self._config

    @property
    def registry(self) -> CollectorRegistry:
        """Get Prometheus registry."""
        return self._registry

    @property
    def router_client(self) -> RouterClientProtocol:
        """Get router client (creates lazily)."""
        if self._router_client is None:
            self._router_client = self._create_router_client()
        return self._router_client

    @property
    def error_handler(self) -> CompositeErrorHandler:
        """Get error handler (creates lazily)."""
        if self._error_handler is None:
            self._error_handler = CompositeErrorHandler.from_config(self._config)
        return self._error_handler

    @property
    def collectors(self) -> list[BaseCollector]:
        """Get initialized collectors."""
        return self._collectors

    def set_router_client(self, client: RouterClientProtocol) -> None:
        """
        Set router client (for testing or custom clients).

        Args:
            client: Router client instance
        """
        self._router_client = client

    def register_collector(self, collector_class: type[BaseCollector]) -> None:
        """
        Register a collector class.

        Args:
            collector_class: The collector class to register
        """
        if collector_class not in self._collector_classes:
            self._collector_classes.append(collector_class)
            logger.debug("Registered collector: %s", collector_class.name)

    def register_collectors(self, *collector_classes: type[BaseCollector]) -> None:
        """
        Register multiple collector classes.

        Args:
            *collector_classes: Collector classes to register
        """
        for collector_class in collector_classes:
            self.register_collector(collector_class)

    def initialize(self) -> None:
        """
        Initialize all registered components.

        Creates instances of all registered collectors.
        Should be called after all collectors are registered.
        """
        if self._initialized:
            logger.warning("Container already initialized")
            return

        self._collectors = []
        for collector_class in self._collector_classes:
            try:
                collector = collector_class(
                    registry=self._registry,
                    config=self._config,
                )
                self._collectors.append(collector)
                logger.info("Initialized collector: %s", collector.name)
            except Exception as e:
                logger.error(
                    "Failed to initialize collector %s: %s",
                    collector_class.name,
                    e
                )

        self._initialized = True
        logger.info("Container initialized with %d collectors", len(self._collectors))

    def collect_metrics(self, router_info: Any) -> None:
        """
        Collect metrics from all enabled collectors.

        Args:
            router_info: Router information for labels
        """
        for collector in self._collectors:
            if collector.enabled:
                try:
                    collector.collect(self.router_client, router_info)
                except Exception as e:
                    logger.error(
                        "Collector %s failed: %s",
                        collector.name,
                        e
                    )
                    # Clear this collector's metrics to avoid stale data
                    try:
                        collector._clear_metrics()
                    except Exception as clear_err:
                        logger.warning(
                            "Failed to clear metrics for %s: %s",
                            collector.name,
                            clear_err
                        )

    def clear_all_metrics(self) -> None:
        """Clear metrics from all collectors to avoid stale data."""
        for collector in self._collectors:
            try:
                collector._clear_metrics()
            except Exception as e:
                logger.warning(
                    "Failed to clear metrics for %s: %s",
                    collector.name,
                    e
                )

    def cleanup(self) -> None:
        """Clean up all collectors and resources."""
        for collector in self._collectors:
            try:
                collector.cleanup()
            except Exception as e:
                logger.warning(
                    "Failed to cleanup collector %s: %s",
                    collector.name,
                    e
                )
        self._collectors = []
        self._initialized = False
        logger.info("Container cleaned up")

    def _create_router_client(self) -> RouterClientProtocol:
        """
        Create router client from configuration.

        Returns:
            Configured router client

        Note:
            This imports the client module to avoid circular imports.
            The actual client class should be provided or imported here.
        """
        # Import here to avoid circular imports
        from ..client.router_client import RouterClientFactory

        host = self._config.get('router.host', '192.168.1.1')
        auth = self._config.get('router.auth', '')

        factory = RouterClientFactory(host)
        return factory.auth(auth)  # type: ignore[return-value]

    def get_enabled_collectors(self) -> list[str]:
        """
        Get names of enabled collectors.

        Returns:
            List of enabled collector names
        """
        return [c.name for c in self._collectors if c.enabled]

    def get_disabled_collectors(self) -> list[str]:
        """
        Get names of disabled collectors.

        Returns:
            List of disabled collector names
        """
        return [c.name for c in self._collectors if not c.enabled]
