#!/usr/bin/env python3
"""
Prometheus exporter for ASUS router metrics.

This module exports various metrics from ASUS routers via Prometheus format.
It collects metrics like CPU usage, memory usage, temperature, uptime, and network throughput.
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

import asus_router_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Metrics Registry
registry = CollectorRegistry()

# Temperature metrics
cpu_temp_gauge = Gauge(
    "asus_router_cpu_temperature_celsius",
    "CPU temperature in Celsius",
    labelnames=["product_id"],
    registry=registry
)

# CPU metrics
cpu_usage_gauge = Gauge(
    "asus_router_cpu_usage",
    "CPU usage",
    labelnames=["product_id", "cpu_id"],
    registry=registry
)

cpu_total_gauge = Gauge(
    "asus_router_cpu_total",
    "CPU total ticks",
    labelnames=["product_id", "cpu_id"],
    registry=registry
)

# Memory metrics
memory_total_bytes = Gauge(
    "asus_router_memory_total_bytes",
    "Total memory in bytes",
    labelnames=["product_id"],
    registry=registry
)

memory_used_bytes = Gauge(
    "asus_router_memory_used_bytes",
    "Used memory in bytes",
    labelnames=["product_id"],
    registry=registry
)

memory_free_bytes = Gauge(
    "asus_router_memory_free_bytes",
    "Free memory in bytes",
    labelnames=["product_id"],
    registry=registry
)

# Uptime metrics
uptime_seconds = Gauge(
    "asus_router_uptime_seconds",
    "Router uptime in seconds",
    labelnames=["product_id"],
    registry=registry
)

# Network throughput metrics - Bridge
bridge_tx_bytes = Gauge(
    "asus_router_bridge_transmit_bytes_total",
    "Total bytes transmitted on bridge interface",
    labelnames=["product_id"],
    registry=registry
)

bridge_rx_bytes = Gauge(
    "asus_router_bridge_receive_bytes_total",
    "Total bytes received on bridge interface",
    labelnames=["product_id"],
    registry=registry
)

# Network throughput metrics - Wired
wired_tx_bytes = Gauge(
    "asus_router_wired_transmit_bytes_total",
    "Total bytes transmitted on wired interface",
    labelnames=["product_id"],
    registry=registry
)

wired_rx_bytes = Gauge(
    "asus_router_wired_receive_bytes_total",
    "Total bytes received on wired interface",
    labelnames=["product_id"],
    registry=registry
)

# Network throughput metrics - Internet
internet_tx_bytes = Gauge(
    "asus_router_internet_transmit_bytes_total",
    "Total bytes transmitted on internet interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

internet_rx_bytes = Gauge(
    "asus_router_internet_receive_bytes_total",
    "Total bytes received on internet interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

# Network throughput metrics - Wireless
wireless_tx_bytes = Gauge(
    "asus_router_wireless_transmit_bytes_total",
    "Total bytes transmitted on wireless interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

wireless_rx_bytes = Gauge(
    "asus_router_wireless_receive_bytes_total",
    "Total bytes received on wireless interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

# Router info metric
router_info = Gauge(
    "asus_router_info",
    "Router information (product ID and other details)",
    labelnames=["product_id"],
    registry=registry
)

# Scrape duration and errors
scrape_duration_seconds = Histogram(
    "asus_router_scrape_duration_seconds",
    "Time spent scraping router metrics",
    registry=registry
)

scrape_errors_total = Counter(
    "asus_router_scrape_errors_total",
    "Total number of scrape errors",
    registry=registry
)


class RouterMetricsCollector:
    """Collects metrics from ASUS router and updates Prometheus metrics."""

    def __init__(self, client: asus_router_client.RouterClient):
        self.client = client
        self.product_id = None

    def collect_all_metrics(self):
        """Collect all available metrics from the router."""
        with scrape_duration_seconds.time():
            try:
                # Collect product_id first as it's used in all metrics
                self._collect_router_info()

                if not self.product_id:
                    logger.warning("Product ID not available, skipping metric collection")
                    return

                self._collect_temperature_metrics()
                self._collect_cpu_metrics()
                self._collect_memory_metrics()
                self._collect_uptime_metrics()
                self._collect_network_metrics()
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                scrape_errors_total.inc()
                raise

    def _collect_temperature_metrics(self):
        """Collect temperature metrics."""
        try:
            temp_info = self.client.core_temp()
            cpu_temp_gauge.labels(product_id=self.product_id).set(temp_info.cpu)
            logger.debug(f"Temperature collected: CPU={temp_info.cpu}C")
        except Exception as e:
            logger.warning(f"Failed to collect temperature metrics: {e}")
            scrape_errors_total.inc()

    def _collect_cpu_metrics(self):
        """Collect CPU usage metrics."""
        try:
            cpu_infos = self.client.cpu_usage()
            for i, cpu_info in enumerate(cpu_infos):
                cpu_usage_gauge.labels(product_id=self.product_id, cpu_id=str(i)).set(cpu_info.usage)
                cpu_total_gauge.labels(product_id=self.product_id, cpu_id=str(i)).set(cpu_info.total)
            logger.debug(f"CPU metrics collected: {len(cpu_infos)} CPUs")
        except Exception as e:
            logger.warning(f"Failed to collect CPU metrics: {e}")
            scrape_errors_total.inc()

    def _collect_memory_metrics(self):
        """Collect memory usage metrics."""
        try:
            mem_info = self.client.memory_usage()
            memory_total_bytes.labels(product_id=self.product_id).set(mem_info.total)
            memory_used_bytes.labels(product_id=self.product_id).set(mem_info.used)
            memory_free_bytes.labels(product_id=self.product_id).set(mem_info.free)
            logger.debug(
                f"Memory collected: total={mem_info.total}, used={mem_info.used}, free={mem_info.free}"
            )
        except Exception as e:
            logger.warning(f"Failed to collect memory metrics: {e}")
            scrape_errors_total.inc()

    def _collect_uptime_metrics(self):
        """Collect uptime metrics."""
        try:
            uptime_info = self.client.uptime()
            uptime_seconds.labels(product_id=self.product_id).set(uptime_info.uptime_sec)
            logger.debug(f"Uptime collected: {uptime_info.uptime_sec}s")
        except Exception as e:
            logger.warning(f"Failed to collect uptime metrics: {e}")
            scrape_errors_total.inc()

    def _collect_network_metrics(self):
        """Collect network throughput metrics."""
        try:
            netdev_info = self.client.netdev()

            # Bridge metrics
            bridge_tx_bytes.labels(product_id=self.product_id).set(netdev_info.bridge.total_upload_bytes)
            bridge_rx_bytes.labels(product_id=self.product_id).set(netdev_info.bridge.total_download_bytes)

            # Wired metrics
            wired_tx_bytes.labels(product_id=self.product_id).set(netdev_info.wired.total_upload_bytes)
            wired_rx_bytes.labels(product_id=self.product_id).set(netdev_info.wired.total_download_bytes)

            # Internet metrics
            for interface_id, throughput in netdev_info.internet.items():
                internet_tx_bytes.labels(product_id=self.product_id, interface_id=str(interface_id)).set(
                    throughput.total_upload_bytes
                )
                internet_rx_bytes.labels(product_id=self.product_id, interface_id=str(interface_id)).set(
                    throughput.total_download_bytes
                )

            # Wireless metrics
            for interface_id, throughput in netdev_info.wireless.items():
                wireless_tx_bytes.labels(product_id=self.product_id, interface_id=str(interface_id)).set(
                    throughput.total_upload_bytes
                )
                wireless_rx_bytes.labels(product_id=self.product_id, interface_id=str(interface_id)).set(
                    throughput.total_download_bytes
                )

            logger.debug(
                f"Network metrics collected: "
                f"internet={len(netdev_info.internet)}, "
                f"wireless={len(netdev_info.wireless)}"
            )
        except Exception as e:
            logger.warning(f"Failed to collect network metrics: {e}")
            scrape_errors_total.inc()

    def _collect_router_info(self):
        """Collect router information."""
        try:
            self.product_id = self.client.productid()
            router_info.labels(product_id=self.product_id).set(1)
            logger.debug(f"Router info collected: product_id={self.product_id}")
        except Exception as e:
            logger.warning(f"Failed to collect router info: {e}")
            scrape_errors_total.inc()


def create_app(router_host: str, router_auth: str, metrics_port: int = 8000):
    """
    Create and configure the Prometheus metrics exporter.

    Args:
        router_host: ASUS router host/IP address
        router_auth: Authentication string (username:password)
        metrics_port: Port to expose metrics on (default: 8000)

    Returns:
        Callable that starts the exporter
    """

    def app():
        logger.info(f"Starting Prometheus exporter on port {metrics_port}")
        logger.info(f"Connecting to router at {router_host}")

        # Initialize router client
        factory = asus_router_client.RouterClientFactory(router_host)
        client = factory.auth(router_auth)

        # Create metrics collector
        collector = RouterMetricsCollector(client)

        # Start Prometheus metrics HTTP server
        start_http_server(metrics_port, registry=registry)
        logger.info(f"Metrics available at http://localhost:{metrics_port}/metrics")

        # Scrape metrics every 30 seconds
        try:
            while True:
                try:
                    collector.collect_all_metrics()
                    logger.info("Metrics collected successfully")
                except Exception as e:
                    logger.error(f"Error during metrics collection: {e}")

                time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Shutting down exporter")

    return app


def main():
    """Main entry point for the Prometheus exporter."""
    # Read defaults from environment variables
    default_router_host = os.getenv("ASUS_ROUTER_HOST")
    default_router_auth = os.getenv("ASUS_ROUTER_AUTH")
    default_metrics_port = int(os.getenv("ASUS_METRICS_PORT", "8000"))
    default_log_level = os.getenv("ASUS_LOG_LEVEL", "INFO")

    parser = argparse.ArgumentParser(
        description="Prometheus exporter for ASUS router metrics",
        epilog="Environment variables can be used as defaults: "
               "ASUS_ROUTER_HOST, ASUS_ROUTER_AUTH, ASUS_METRICS_PORT, ASUS_LOG_LEVEL"
    )
    parser.add_argument(
        "--router-host",
        default=default_router_host,
        required=not default_router_host,
        help="ASUS router host or IP address (e.g., 192.168.1.1 or http://192.168.1.1) "
             "[env: ASUS_ROUTER_HOST]"
    )
    parser.add_argument(
        "--router-auth",
        default=default_router_auth,
        required=not default_router_auth,
        help="Router authentication (format: username:password) [env: ASUS_ROUTER_AUTH]"
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=default_metrics_port,
        help="Port to expose Prometheus metrics on (default: 8000) [env: ASUS_METRICS_PORT]"
    )
    parser.add_argument(
        "--log-level",
        default=default_log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO) [env: ASUS_LOG_LEVEL]"
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.router_host:
        parser.error("--router-host is required or set ASUS_ROUTER_HOST environment variable")
    if not args.router_auth:
        parser.error("--router-auth is required or set ASUS_ROUTER_AUTH environment variable")

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Create and run app
    app = create_app(args.router_host, args.router_auth, args.metrics_port)
    app()


if __name__ == "__main__":
    main()
