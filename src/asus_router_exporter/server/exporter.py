"""
Prometheus Exporter HTTP Server.

Provides the main exporter application that:
- Starts Prometheus HTTP server
- Periodically collects metrics from the router
- Handles graceful shutdown
"""

from __future__ import annotations

import errno
import logging
import signal
import threading
import time
from dataclasses import dataclass, field
from http.server import HTTPServer
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

    Provides safe defaults for commonly accessed attributes. This class
    intentionally does NOT include all RouterInfo fields - only those
    needed for basic operation when the router is unreachable.

    IMPORTANT: Collectors MUST use `getattr(router_info, 'field', default)`
    when accessing router_info attributes, not direct attribute access.
    This ensures graceful handling when FallbackRouterInfo is used and
    prevents AttributeError for fields not defined here.
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
        self._shutdown_event = threading.Event()
        self._router_info: Any | None = None
        self._http_server: HTTPServer | None = None
        self._received_signal: int | None = None

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
        # Note: Signal handlers must not call logging functions because Python's
        # logging module uses locks internally. If a signal interrupts code that
        # holds the logging lock, calling logger from the handler causes deadlock.
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Start HTTP server with error handling for port-in-use
        try:
            httpd, _ = start_http_server(port, registry=self._container.registry)
            self._http_server = httpd
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                logger.error("Port %d is already in use. Choose a different port.", port)
                raise SystemExit(1) from e
            raise
        logger.info("Metrics available at http://localhost:%d/metrics", port)

        # Collect initial router info
        self._collect_router_info()

        # Start collection loop
        logger.info(
            "Starting metric collection (interval: %ds, collectors: %s)",
            interval,
            ", ".join(self._container.get_enabled_collectors()),
        )

        try:
            while not self._shutdown_event.is_set():
                self._collect_with_error_handling()
                # Use Event.wait() instead of time.sleep() to allow immediate
                # response to shutdown signals without waiting for the full interval
                self._shutdown_event.wait(timeout=interval)
        except KeyboardInterrupt:
            # Safety net for KeyboardInterrupt that may occur in edge cases:
            # - During signal handler setup (before _handle_shutdown is installed)
            # - During certain system calls that don't respect signal handlers
            # Normally SIGINT triggers _handle_shutdown which sets shutdown_event,
            # causing the while loop to exit cleanly.
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
        except Exception:
            logger.exception("Failed to get router info")
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
        except Exception:
            logger.exception("Metric collection failed")
            # Failure - set up=0 and clear all collector metrics
            self._up.labels(product_id=product_id).set(0)
            self._container.clear_all_metrics()
        finally:
            duration = time.time() - start_time
            self._scrape_duration.labels(product_id=product_id).set(duration)

    def _collect_metrics(self) -> None:
        """Collect metrics from all collectors.

        Refreshes router info on each cycle to ensure up-to-date data
        (uptime, port status, etc.).

        Raises:
            RuntimeError: If all enabled collectors failed
        """
        # Clear the router client cache first to ensure fresh data,
        # then refresh router info before collecting metrics.
        client = self._container.router_client
        client.clear_cache()

        # Refresh router info each cycle to get updated uptime, port status, etc.
        self._refresh_router_info(client)

        success = self._container.collect_metrics(self._router_info)
        if not success:
            raise RuntimeError("All collectors failed")

    def _refresh_router_info(self, client: Any) -> None:
        """Refresh router info for the current collection cycle.

        Args:
            client: Router client instance to use for fetching info.

        Updates self._router_info with fresh data from the router.
        Falls back to previous router_info (or FallbackRouterInfo) on error.
        """
        try:
            self._router_info = client.get_info()
        except Exception:
            logger.warning("Failed to refresh router info, using previous values", exc_info=True)
            # Keep existing router_info (or FallbackRouterInfo if never succeeded)

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """
        Handle shutdown signal.

        SAFETY: This handler must NOT call logging functions. Python's logging
        uses locks internally, and if this signal handler interrupts code that
        holds the logging lock, calling logger here would cause a deadlock.
        Only safe operations are: setting flags/events, writing to pipes/sockets.
        """
        self._received_signal = signum
        self._shutdown_event.set()

    def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        # Log signal info here (safe, outside signal handler)
        if self._received_signal is not None:
            logger.info("Received shutdown signal (%d)", self._received_signal)
        logger.info("Shutting down exporter...")

        # Stop HTTP server to cleanly terminate in-flight requests
        if self._http_server is not None:
            self._http_server.shutdown()
            logger.debug("HTTP server stopped")

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
