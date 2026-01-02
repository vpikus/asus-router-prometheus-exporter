"""
Network device metrics collector.

Collects throughput metrics for:
- Bridge interface
- Wired interface
- Internet interfaces
- Wireless interfaces
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import CollectorRegistry, Counter

from ..core.protocols import ConfigProviderProtocol, RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class NetdevCollector(BaseCollector):
    """
    Collector for network device throughput metrics.

    Metrics:
    - asus_router_netdev_bridge_transmit_bytes_total
    - asus_router_netdev_bridge_receive_bytes_total
    - asus_router_netdev_wired_transmit_bytes_total
    - asus_router_netdev_wired_receive_bytes_total
    - asus_router_netdev_internet_transmit_bytes_total
    - asus_router_netdev_internet_receive_bytes_total
    - asus_router_netdev_wireless_transmit_bytes_total
    - asus_router_netdev_wireless_receive_bytes_total
    """

    name = "netdev"

    def __init__(
        self,
        registry: CollectorRegistry,
        config: ConfigProviderProtocol,
    ):
        self._previous_samples: dict[str, dict[str, int]] = {}
        super().__init__(registry, config)

    def _create_metrics(self) -> None:
        """Create network device metrics."""
        # Bridge metrics
        self._bridge_tx = Counter(
            "asus_router_netdev_bridge_transmit_bytes_total",
            "Total bytes transmitted on bridge interface",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._bridge_tx)

        self._bridge_rx = Counter(
            "asus_router_netdev_bridge_receive_bytes_total",
            "Total bytes received on bridge interface",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._bridge_rx)

        # Wired metrics
        self._wired_tx = Counter(
            "asus_router_netdev_wired_transmit_bytes_total",
            "Total bytes transmitted on wired interface",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._wired_tx)

        self._wired_rx = Counter(
            "asus_router_netdev_wired_receive_bytes_total",
            "Total bytes received on wired interface",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._wired_rx)

        # Internet metrics (with interface_id label)
        self._internet_tx = Counter(
            "asus_router_netdev_internet_transmit_bytes_total",
            "Total bytes transmitted on internet interface",
            ["product_id", "interface_id"],
            registry=self._registry,
        )
        self._register_metric(self._internet_tx)

        self._internet_rx = Counter(
            "asus_router_netdev_internet_receive_bytes_total",
            "Total bytes received on internet interface",
            ["product_id", "interface_id"],
            registry=self._registry,
        )
        self._register_metric(self._internet_rx)

        # Wireless metrics (with interface_id label)
        self._wireless_tx = Counter(
            "asus_router_netdev_wireless_transmit_bytes_total",
            "Total bytes transmitted on wireless interface",
            ["product_id", "interface_id"],
            registry=self._registry,
        )
        self._register_metric(self._wireless_tx)

        self._wireless_rx = Counter(
            "asus_router_netdev_wireless_receive_bytes_total",
            "Total bytes received on wireless interface",
            ["product_id", "interface_id"],
            registry=self._registry,
        )
        self._register_metric(self._wireless_rx)

    def _collect_metrics(
        self,
        router_client: RouterClientProtocol,
        router_info: Any
    ) -> None:
        """Collect network device metrics from router."""
        product_id = getattr(router_info, 'product_id', 'unknown')

        try:
            netdev_info = router_client.get_netdev()
        except Exception as e:
            logger.warning("[%s] Network collection failed: %s", product_id, e)
            return

        is_first_sample = not self._previous_samples

        # First sample: initialize tracking and counters (with 0 increment to register labels)
        if is_first_sample:
            self._previous_samples = self._create_network_samples(netdev_info)
            # Initialize counters with labels so they appear in metrics output
            self._initialize_counters(product_id, netdev_info)
            logger.debug("[%s] Network samples initialized (first collection)", product_id)
            return

        # Bridge metrics
        self._collect_simple_interface(
            "bridge", product_id, netdev_info.bridge,
            self._bridge_tx, self._bridge_rx
        )

        # Wired metrics
        self._collect_simple_interface(
            "wired", product_id, netdev_info.wired,
            self._wired_tx, self._wired_rx
        )

        # Internet metrics (multiple interfaces)
        self._collect_multi_interface(
            "internet", product_id, netdev_info.internet,
            self._internet_tx, self._internet_rx
        )

        # Wireless metrics (multiple interfaces)
        self._collect_multi_interface(
            "wireless", product_id, netdev_info.wireless,
            self._wireless_tx, self._wireless_rx
        )

        # Update previous samples
        self._previous_samples = self._create_network_samples(netdev_info)

        logger.debug(
            "[%s] Network metrics collected: internet=%d, wireless=%d",
            product_id,
            len(netdev_info.internet) if netdev_info.internet else 0,
            len(netdev_info.wireless) if netdev_info.wireless else 0
        )

    def _initialize_counters(self, product_id: str, netdev_info: Any) -> None:
        """Initialize counters with labels so they appear in metrics output."""
        # Bridge counters
        if netdev_info.bridge:
            self._bridge_tx.labels(product_id=product_id).inc(0)
            self._bridge_rx.labels(product_id=product_id).inc(0)

        # Wired counters
        if netdev_info.wired:
            self._wired_tx.labels(product_id=product_id).inc(0)
            self._wired_rx.labels(product_id=product_id).inc(0)

        # Internet counters
        if netdev_info.internet:
            for iface_id in netdev_info.internet.keys():
                self._internet_tx.labels(product_id=product_id, interface_id=str(iface_id)).inc(0)
                self._internet_rx.labels(product_id=product_id, interface_id=str(iface_id)).inc(0)

        # Wireless counters
        if netdev_info.wireless:
            for iface_id in netdev_info.wireless.keys():
                self._wireless_tx.labels(product_id=product_id, interface_id=str(iface_id)).inc(0)
                self._wireless_rx.labels(product_id=product_id, interface_id=str(iface_id)).inc(0)

    def _collect_simple_interface(
        self,
        iface_type: str,
        product_id: str,
        current: Any,
        tx_counter: Counter,
        rx_counter: Counter
    ) -> None:
        """Collect metrics for a simple interface (no interface_id)."""
        prev = self._previous_samples.get(iface_type, {})

        if current is None:
            return

        tx = getattr(current, 'total_upload_bytes', 0)
        rx = getattr(current, 'total_download_bytes', 0)

        prev_tx = prev.get("tx", 0)
        prev_rx = prev.get("rx", 0)

        delta_tx = self._calculate_delta(tx, prev_tx)
        delta_rx = self._calculate_delta(rx, prev_rx)

        # Always call inc() to ensure consistent data points for rate() calculation
        tx_counter.labels(product_id=product_id).inc(delta_tx)
        rx_counter.labels(product_id=product_id).inc(delta_rx)

    def _collect_multi_interface(
        self,
        iface_type: str,
        product_id: str,
        interfaces: dict,
        tx_counter: Counter,
        rx_counter: Counter
    ) -> None:
        """Collect metrics for interfaces with interface_id label."""
        if not interfaces:
            return

        prev_interfaces: dict[str, dict[str, int]] = self._previous_samples.get(iface_type, {})  # type: ignore[assignment]

        for iface_id, current in interfaces.items():
            prev: dict[str, int] = prev_interfaces.get(str(iface_id), {})

            tx = getattr(current, 'total_upload_bytes', 0)
            rx = getattr(current, 'total_download_bytes', 0)

            prev_tx = prev.get("tx", 0)
            prev_rx = prev.get("rx", 0)

            delta_tx = self._calculate_delta(tx, prev_tx)
            delta_rx = self._calculate_delta(rx, prev_rx)

            # Always call inc() to ensure consistent data points for rate() calculation
            tx_counter.labels(product_id=product_id, interface_id=str(iface_id)).inc(delta_tx)
            rx_counter.labels(product_id=product_id, interface_id=str(iface_id)).inc(delta_rx)

    def _create_network_samples(self, netdev_info: Any) -> dict:
        """Create a snapshot of current network samples for delta calculation."""
        samples: dict[str, Any] = {}

        if netdev_info.bridge:
            samples["bridge"] = {
                "tx": getattr(netdev_info.bridge, 'total_upload_bytes', 0),
                "rx": getattr(netdev_info.bridge, 'total_download_bytes', 0)
            }

        if netdev_info.wired:
            samples["wired"] = {
                "tx": getattr(netdev_info.wired, 'total_upload_bytes', 0),
                "rx": getattr(netdev_info.wired, 'total_download_bytes', 0)
            }

        if netdev_info.internet:
            samples["internet"] = {}
            for iface_id, iface in netdev_info.internet.items():
                samples["internet"][iface_id] = {
                    "tx": getattr(iface, 'total_upload_bytes', 0),
                    "rx": getattr(iface, 'total_download_bytes', 0)
                }

        if netdev_info.wireless:
            samples["wireless"] = {}
            for iface_id, iface in netdev_info.wireless.items():
                samples["wireless"][iface_id] = {
                    "tx": getattr(iface, 'total_upload_bytes', 0),
                    "rx": getattr(iface, 'total_download_bytes', 0)
                }

        return samples

    @staticmethod
    def _calculate_delta(current: int, previous: int) -> int:
        """Calculate delta, handling counter wraps."""
        if current >= previous:
            return current - previous
        # Counter wrapped, skip this sample
        return 0

    def cleanup(self) -> None:
        """Clean up collector and reset state."""
        super().cleanup()
        self._previous_samples.clear()
