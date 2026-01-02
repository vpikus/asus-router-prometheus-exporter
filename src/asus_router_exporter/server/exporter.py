"""
Prometheus Exporter HTTP Server.

Provides the main exporter application that:
- Starts Prometheus HTTP server
- Periodically collects metrics from the router
- Handles graceful shutdown
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prometheus_client import Gauge, start_http_server

from ..core.container import Container

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class FallbackRouterInfo:
    """
    Minimal router info used when actual router info cannot be retrieved.

    Provides safe defaults for all attributes that collectors might access.
    """

    product_id: str = "unknown"
    lan_hwaddr: str = ""
    lan_hostname: str = ""
    firmver: str = ""
    extendno: str = ""
    serial_no: str = ""
    sw_mode: Any = None
    uptime: Any = None
    reboot_schedule: Any = None
    software_update_available: bool = False
    ports_info: list = field(default_factory=list)


class Exporter:
    """
    Main Prometheus exporter application.

    Manages the lifecycle of metric collection:
    - Starts HTTP server for Prometheus scraping
    - Periodically collects metrics from router
    - Handles errors with retry and circuit breaker
    - Supports graceful shutdown

    Example:
        container = Container.from_config("config.yaml")
        container.register_collectors(CPUCollector, MemoryCollector)
        container.initialize()

        exporter = Exporter(container)
        exporter.run()
    """

    def __init__(self, container: Container):
        """
        Initialize exporter.

        Args:
            container: Dependency injection container
        """
        self._container = container
        self._running = False
        self._router_info: Any | None = None

        # Scrape status metrics
        self._up = Gauge(
            "asus_router_up",
            "Whether the last scrape was successful (1=success, 0=failure)",
            ["product_id"],
            registry=container.registry,
        )
        self._scrape_duration = Gauge(
            "asus_router_scrape_duration_seconds",
            "Duration of the last scrape in seconds",
            ["product_id"],
            registry=container.registry,
        )

    def run(self) -> None:
        """
        Run the exporter.

        Starts the HTTP server and begins metric collection loop.
        Blocks until shutdown signal is received.
        """
        config = self._container.config
        port = config.get("exporter.port", 8000)
        interval = config.get("exporter.scrape_interval", 30)

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Start HTTP server
        start_http_server(port, registry=self._container.registry)
        logger.info("Metrics available at http://localhost:%d/metrics", port)

        # Collect initial router info
        self._collect_router_info()

        # Start collection loop
        self._running = True
        logger.info(
            "Starting metric collection (interval: %ds, collectors: %s)",
            interval,
            ", ".join(self._container.get_enabled_collectors()),
        )

        try:
            while self._running:
                self._collect_with_error_handling()
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _collect_router_info(self) -> None:
        """Collect and store router information."""
        try:
            client = self._container.router_client
            self._router_info = client.get_info()
            product_id = getattr(self._router_info, "product_id", "unknown")
            logger.info("Connected to router: %s", product_id)
        except Exception as e:
            logger.error("Failed to get router info: %s", e)
            # Create minimal router info for labels with safe defaults
            self._router_info = FallbackRouterInfo()

    def _collect_with_error_handling(self) -> None:
        """Collect metrics with error handling and status tracking."""
        error_handler = self._container.error_handler
        product_id = getattr(self._router_info, "product_id", "unknown")
        start_time = time.time()

        try:
            error_handler.execute(self._collect_metrics)
            # Success
            self._up.labels(product_id=product_id).set(1)
        except Exception as e:
            logger.error("Metric collection failed: %s", e)
            # Failure - set up=0 and clear all collector metrics
            self._up.labels(product_id=product_id).set(0)
            self._container.clear_all_metrics()
        finally:
            duration = time.time() - start_time
            self._scrape_duration.labels(product_id=product_id).set(duration)

    def _collect_metrics(self) -> None:
        """Collect metrics from all collectors."""
        self._container.collect_metrics(self._router_info)

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal."""
        logger.info("Received shutdown signal (%d)", signum)
        self._running = False

    def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Shutting down exporter...")
        self._container.cleanup()
        logger.info("Exporter stopped")


def create_exporter(
    config_path: str | None = None,
    router_host: str | None = None,
    router_auth: str | None = None,
    metrics_port: int | None = None,
) -> Exporter:
    """
    Create and configure exporter.

    Args:
        config_path: Path to YAML configuration file
        router_host: Router hostname/IP (overrides config)
        router_auth: Router auth token (overrides config)
        metrics_port: Metrics port (overrides config)

    Returns:
        Configured Exporter instance
    """
    from ..collectors import DEFAULT_COLLECTORS

    # Create container
    if config_path:
        container = Container.from_config(config_path)
    else:
        container = Container.from_env()

    # Apply CLI overrides using proper setter
    if router_host:
        container.config.set("router.host", router_host)
    if router_auth:
        container.config.set("router.auth", router_auth)
    if metrics_port:
        container.config.set("exporter.port", metrics_port)

    # Register all default collectors
    container.register_collectors(*DEFAULT_COLLECTORS)  # type: ignore[type-abstract]

    # Initialize container
    container.initialize()

    return Exporter(container)
