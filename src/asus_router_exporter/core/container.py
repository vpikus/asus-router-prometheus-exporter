"""
Dependency injection container for the ASUS Router Exporter.

Manages the creation and lifecycle of all application components,
providing loose coupling and easy testability.
"""

from __future__ import annotations

import errno
import logging
import time
from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY, CollectorRegistry

from ..metrics.self_metrics import SelfMetrics
from .config import Config
from .error_handling import CompositeErrorHandler
from .exceptions import RouterConnectionError
from .protocols import RouterClientProtocol

if TYPE_CHECKING:
    from ..collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# Cache requests.ConnectionError at module level to avoid repeated import overhead.
# Falls back to a type that never matches if requests is not installed.
try:
    from requests.exceptions import ConnectionError as RequestsConnectionError
except ImportError:
    RequestsConnectionError = type(None)  # type: ignore[misc,assignment]

# Connection-related errno values (platform-independent via errno module)
CONNECTION_ERRNOS = (
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ETIMEDOUT,
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
)


class Container:
    """
    Dependency injection container.

    Manages the lifecycle of all application components:
    - Configuration
    - Router client
    - Error handling
    - Metric collectors
    - Prometheus registry

    Threading Model:
        The application runs with two threads:
        1. Main thread: Runs metric collection loop (owns Container, collectors)
        2. HTTP thread: Spawned by start_http_server() for Prometheus scrapes

        This container's lazy properties (router_client, error_handler) are NOT
        thread-safe, but this is safe because they are only accessed from the
        main thread during collection. The Prometheus HTTP thread only reads
        metric values, which is thread-safe at the prometheus_client level.

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
        failed_collectors: list[str] = []
        for collector_class in self._collector_classes:
            try:
                collector = collector_class(
                    registry=self._registry,
                    config=self._config,
                )
                self._collectors.append(collector)
                logger.info("Initialized collector: %s", collector.name)
            except Exception:
                logger.exception("Failed to initialize collector %s", collector_class.name)
                failed_collectors.append(collector_class.name)

        self._initialized = True

        # Log summary including any failures
        if failed_collectors:
            logger.warning(
                "Container initialized with %d collectors (%d failed: %s)",
                len(self._collectors),
                len(failed_collectors),
                ", ".join(failed_collectors),
            )
        else:
            logger.info("Container initialized with %d collectors", len(self._collectors))

    def collect_metrics(self, router_info: Any) -> bool:
        """
        Collect metrics from all enabled collectors.

        Args:
            router_info: Router information for labels

        Returns:
            True if at least one enabled collector succeeded, False if all failed.
            Also returns True if there are no enabled collectors (nothing failed).

        Raises:
            RouterConnectionError: Raised when a connection error is detected
                (router unreachable). The original exception is preserved as
                ``__cause__``. Has ``recoverable=False`` to skip retries and
                trigger the circuit breaker immediately.

        Note:
            When a connection error is detected, remaining collectors are skipped
            to avoid redundant failed attempts.

            Cache clearing is the caller's responsibility. The Exporter clears
            the cache before refreshing router info to ensure fresh data.
        """
        enabled_collectors = [c for c in self._collectors if c.enabled]
        if not enabled_collectors:
            return True  # Nothing to collect, nothing failed

        success_count = 0
        metrics = SelfMetrics.get_instance()
        total_collectors = len(enabled_collectors)

        for idx, collector in enumerate(enabled_collectors):
            start_time = time.time()
            try:
                collector.collect(self.router_client, router_info)
                duration = time.time() - start_time
                metrics.record_collector_success(collector.name)
                metrics.set_collector_duration(collector.name, duration)
                success_count += 1
            except Exception as e:
                duration = time.time() - start_time
                metrics.record_collector_error(collector.name)
                metrics.set_collector_duration(collector.name, duration)
                logger.exception("Collector %s failed", collector.name)
                # Clear this collector's metrics to avoid stale data
                try:
                    collector.clear_metrics()
                except Exception:
                    logger.warning("Failed to clear metrics for %s", collector.name, exc_info=True)

                # Short-circuit on connection errors - if router is unreachable,
                # skip remaining collectors to avoid redundant failed attempts.
                # Wrap in RouterConnectionError with recoverable=False to skip
                # retries and trigger circuit breaker immediately.
                if self._is_connection_error(e):
                    remaining = total_collectors - idx - 1
                    if remaining > 0:
                        logger.warning("Router unreachable, skipping %d remaining collectors", remaining)
                    raise RouterConnectionError(
                        f"Router unreachable: {e}",
                        recoverable=False,
                    ) from e

        if success_count == 0:
            logger.error("All %d enabled collectors failed", len(enabled_collectors))

        return success_count > 0

    def _is_connection_error(self, error: Exception) -> bool:
        """
        Check if an exception indicates a connection failure.

        Args:
            error: The exception to check

        Returns:
            True if the error indicates the router is unreachable
        """
        # Traverse exception chain using DFS to explore both __cause__ and __context__
        # Use visited set to prevent infinite loops from malformed exception chains
        stack: list[BaseException] = [error]
        visited: set[int] = set()

        while stack:
            current = stack.pop()
            exc_id = id(current)
            if exc_id in visited:
                continue
            visited.add(exc_id)

            # Check requests.ConnectionError first (it's a subclass of OSError)
            if isinstance(current, RequestsConnectionError):
                return True
            # Check Python's built-in ConnectionError
            if isinstance(current, ConnectionError):
                return True
            # Check OSError with specific errnos
            if isinstance(current, OSError) and current.errno in CONNECTION_ERRNOS:
                return True

            # Add both __cause__ and __context__ to stack for exploration
            if current.__cause__ is not None:
                stack.append(current.__cause__)
            if current.__context__ is not None:
                stack.append(current.__context__)

        return False

    def clear_all_metrics(self) -> None:
        """Clear metrics from all collectors to avoid stale data."""
        for collector in self._collectors:
            try:
                collector.clear_metrics()
            except Exception:
                logger.warning("Failed to clear metrics for %s", collector.name, exc_info=True)

    def cleanup(self) -> None:
        """Clean up all collectors and resources."""
        for collector in self._collectors:
            try:
                collector.cleanup()
            except Exception:
                logger.warning("Failed to cleanup collector %s", collector.name, exc_info=True)
        self._collectors = []
        self._initialized = False

        # Close router client session to release HTTP connections
        if self._router_client is not None:
            try:
                if hasattr(self._router_client, "close"):
                    self._router_client.close()
            except Exception:
                logger.warning("Failed to close router client", exc_info=True)
            self._router_client = None

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
        from ..client import RouterClientFactory

        host = self._config.get("router.host", "192.168.1.1")
        auth = self._config.get("router.auth", "")
        reauth_interval = self._config.get("router.reauth_interval", 1800)

        factory = RouterClientFactory(host, reauth_interval=reauth_interval)
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
