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
from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

import asus_router_client


@dataclass
class ThroughputSample:
    """Sample of throughput metrics at a point in time."""
    tx: int
    rx: int

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

# CPU metrics (cumulative counters since boot)
cpu_usage_counter = Counter(
    "asus_router_cpu_usage",
    "Busy time (user+system+irq+...) in jiffies/ticks since boot",
    labelnames=["product_id", "cpu_id"],
    registry=registry
)

cpu_total_counter = Counter(
    "asus_router_cpu_total",
    "Total time units (jiffies/ticks) elapsed since boot",
    labelnames=["product_id", "cpu_id"],
    registry=registry
)

# CPU usage percentage (computed from deltas between samples)
cpu_usage_percent_gauge = Gauge(
    "asus_router_cpu_usage_percent",
    "CPU usage percentage (Δusage / Δtotal * 100)",
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
bridge_tx_bytes = Counter(
    "asus_router_netdev_bridge_transmit_bytes_total",
    "Total bytes transmitted on bridge interface",
    labelnames=["product_id"],
    registry=registry
)

bridge_rx_bytes = Counter(
    "asus_router_netdev_bridge_receive_bytes_total",
    "Total bytes received on bridge interface",
    labelnames=["product_id"],
    registry=registry
)

# Network throughput metrics - Wired
wired_tx_bytes = Counter(
    "asus_router_netdev_wired_transmit_bytes_total",
    "Total bytes transmitted on wired interface",
    labelnames=["product_id"],
    registry=registry
)

wired_rx_bytes = Counter(
    "asus_router_netdev_wired_receive_bytes_total",
    "Total bytes received on wired interface",
    labelnames=["product_id"],
    registry=registry
)

# Network throughput metrics - Internet
internet_tx_bytes = Counter(
    "asus_router_netdev_internet_transmit_bytes_total",
    "Total bytes transmitted on internet interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

internet_rx_bytes = Counter(
    "asus_router_netdev_internet_receive_bytes_total",
    "Total bytes received on internet interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

# Network throughput metrics - Wireless
wireless_tx_bytes = Counter(
    "asus_router_netdev_wireless_transmit_bytes_total",
    "Total bytes transmitted on wireless interface",
    labelnames=["product_id", "interface_id"],
    registry=registry
)

wireless_rx_bytes = Counter(
    "asus_router_netdev_wireless_receive_bytes_total",
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

    CANDIDATE_WRAP_BITS = (64, 48, 32)

    def __init__(self, client: asus_router_client.RouterClient):
        self.client = client
        self.product_id = None
        # Track previous CPU samples for percentage calculation
        # Format: {cpu_id: {"usage": value, "total": value}}
        self.previous_cpu_samples = {}
        # Track previous network samples for delta calculation
        # Format: {
        #     "bridge": ThroughputSample,
        #     "wired": ThroughputSample,
        #     "internet": {interface_id: ThroughputSample},
        #     "wireless": {interface_id: ThroughputSample}
        # }
        self.previous_network_samples = {}

    @staticmethod
    def _calculate_delta(current: int, previous: int) -> int:
        """
        Robust delta between two cumulative counters.
        - Handles 64/48/32-bit wrap-around.
        - Falls back to 'reset' semantics if we can't infer wrap.
        - Never returns negative.
        """
        if current >= previous:
            return current - previous

        # Try plausible wrap moduli (64 -> 48 -> 32)
        for bits in RouterMetricsCollector.CANDIDATE_WRAP_BITS:
            modulus = 1 << bits  # 2**bits
            if previous < modulus:  # plausible previous value for this width
                delta = current + (modulus - previous)
                if delta >= 0:
                    return delta

        # If we get here, treat as a reset (e.g., reboot or interface reset)
        # Choose either:
        #   return current        # start counting from current value
        # or:
        #   return 0              # emit no delta on reset
        return current

    @staticmethod
    def _create_network_samples(netdev_info: asus_router_client.NetdevInfo) -> dict:
        """
        Create network samples from current netdev info.

        Args:
            netdev_info: Current network device information

        Returns:
            Dictionary with network samples for all interfaces
        """
        return {
            "bridge": ThroughputSample(
                tx=netdev_info.bridge.total_upload_bytes,
                rx=netdev_info.bridge.total_download_bytes
            ),
            "wired": ThroughputSample(
                tx=netdev_info.wired.total_upload_bytes,
                rx=netdev_info.wired.total_download_bytes
            ),
            "internet": {
                iid: ThroughputSample(
                    tx=throughput.total_upload_bytes,
                    rx=throughput.total_download_bytes
                )
                for iid, throughput in netdev_info.internet.items()
            },
            "wireless": {
                wid: ThroughputSample(
                    tx=throughput.total_upload_bytes,
                    rx=throughput.total_download_bytes
                )
                for wid, throughput in netdev_info.wireless.items()
            }
        }

    def _update_interface_metrics(self, interface_type: str, interfaces: dict,
                                 prev_interfaces: dict, tx_counter, rx_counter) -> None:
        """
        Update metrics for a specific interface type (internet or wireless).

        Args:
            interface_type: Type of interface ("internet" or "wireless")
            interfaces: Current interface data from netdev_info
            prev_interfaces: Previous interface samples
            tx_counter: Prometheus counter for transmit bytes
            rx_counter: Prometheus counter for receive bytes
        """
        for interface_id, throughput in interfaces.items():
            if interface_id in prev_interfaces:
                prev_iface = prev_interfaces[interface_id]
                delta_tx = self._calculate_delta(throughput.total_upload_bytes, prev_iface.tx)
                delta_rx = self._calculate_delta(throughput.total_download_bytes, prev_iface.rx)
            else:
                logger.debug(f"{interface_type.capitalize()} interface {interface_id} - first sample, storing baseline")
                delta_tx = 0
                delta_rx = 0

            tx_counter.labels(product_id=self.product_id, interface_id=str(interface_id)).inc(delta_tx)
            rx_counter.labels(product_id=self.product_id, interface_id=str(interface_id)).inc(delta_rx)

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
                cpu_id = str(i)

                # Compute CPU usage percentage from deltas between samples
                if cpu_id in self.previous_cpu_samples:
                    prev_sample = self.previous_cpu_samples[cpu_id]
                    delta_usage = cpu_info.usage - prev_sample["usage"]
                    delta_total = cpu_info.total - prev_sample["total"]

                    cpu_usage_counter.labels(product_id=self.product_id, cpu_id=cpu_id).inc(delta_usage)
                    cpu_total_counter.labels(product_id=self.product_id, cpu_id=cpu_id).inc(delta_total)

                    if delta_total > 0:
                        usage_percent = (delta_usage / delta_total) * 100
                        # Clamp percentage to [0, 100] range
                        usage_percent = max(0, min(100, usage_percent))
                        cpu_usage_percent_gauge.labels(
                            product_id=self.product_id, cpu_id=cpu_id
                        ).set(usage_percent)
                        logger.debug(f"CPU {cpu_id} usage: {usage_percent:.1f}%")

                # Store current sample for next iteration
                self.previous_cpu_samples[cpu_id] = {
                    "usage": cpu_info.usage,
                    "total": cpu_info.total
                }

            logger.debug(f"CPU metrics collected: {len(cpu_infos)} CPUs")
        except Exception as e:
            logger.warning(f"Failed to collect CPU metrics: {e}")
            scrape_errors_total.inc()

    def _collect_memory_metrics(self):
        """Collect memory usage metrics."""
        try:
            mem_info = self.client.memory_usage()
            # ASUS API returns memory values in kilobytes, convert to bytes
            memory_total_bytes.labels(product_id=self.product_id).set(mem_info.total_kb * 1024)
            memory_used_bytes.labels(product_id=self.product_id).set(mem_info.used_kb * 1024)
            memory_free_bytes.labels(product_id=self.product_id).set(mem_info.free_kb * 1024)
            logger.debug(
                f"Memory collected: total={mem_info.total_kb}KB, used={mem_info.used_kb}KB, free={mem_info.free_kb}KB"
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

            # Initialize network samples tracking if not present
            if not self.previous_network_samples:
                self.previous_network_samples = self._create_network_samples(netdev_info)
                logger.debug("Network samples initialized (first collection)")
                return

            # Bridge metrics
            prev_bridge = self.previous_network_samples["bridge"]
            delta_bridge_tx = self._calculate_delta(netdev_info.bridge.total_upload_bytes, prev_bridge.tx)
            delta_bridge_rx = self._calculate_delta(netdev_info.bridge.total_download_bytes, prev_bridge.rx)
            bridge_tx_bytes.labels(product_id=self.product_id).inc(delta_bridge_tx)
            bridge_rx_bytes.labels(product_id=self.product_id).inc(delta_bridge_rx)

            # Wired metrics
            prev_wired = self.previous_network_samples["wired"]
            delta_wired_tx = self._calculate_delta(netdev_info.wired.total_upload_bytes, prev_wired.tx)
            delta_wired_rx = self._calculate_delta(netdev_info.wired.total_download_bytes, prev_wired.rx)
            wired_tx_bytes.labels(product_id=self.product_id).inc(delta_wired_tx)
            wired_rx_bytes.labels(product_id=self.product_id).inc(delta_wired_rx)

            # Internet metrics
            prev_internet = self.previous_network_samples.get("internet", {})
            self._update_interface_metrics("internet", netdev_info.internet, prev_internet,
                                          internet_tx_bytes, internet_rx_bytes)

            # Wireless metrics
            prev_wireless = self.previous_network_samples.get("wireless", {})
            self._update_interface_metrics("wireless", netdev_info.wireless, prev_wireless,
                                          wireless_tx_bytes, wireless_rx_bytes)

            # Update previous samples for next iteration
            self.previous_network_samples = self._create_network_samples(netdev_info)

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
            raise


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
                    raise

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
