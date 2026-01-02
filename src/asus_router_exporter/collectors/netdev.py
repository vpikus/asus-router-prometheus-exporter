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
        # Track active interface IDs to detect and remove stale metrics
        self._active_internet_ids: set[str] = set()
        self._active_wireless_ids: set[str] = set()
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

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect network device metrics from router."""
        product_id = getattr(router_info, "product_id", "unknown")

        try:
            netdev_info = router_client.get_netdev()
        except Exception:
            logger.warning("[%s] Network collection failed", product_id, exc_info=True)
            # Clear metrics but preserve state (_previous_samples, tracking sets).
            #
            # Design Note: We intentionally keep _previous_samples across failures because:
            # 1. Delta calculation uses router values (current - previous), not counter values
            # 2. Keeping previous samples allows correct delta calculation on recovery,
            #    capturing traffic that occurred during the failure window
            # 3. Router reboot during failure is handled by _calculate_delta returning 0
            #    when current < previous (counter wrap detection)
            # 4. Stale interface detection still works on recovery using the tracking sets
            #
            # Only the Prometheus metrics are cleared to indicate no data during failure.
            self._clear_metrics()
            return

        is_first_sample = not self._previous_samples

        # First sample: initialize tracking and counters (with 0 increment to register labels)
        if is_first_sample:
            self._previous_samples = self._create_network_samples(netdev_info)
            # Initialize counters with labels so they appear in metrics output
            self._initialize_counters(product_id, netdev_info)
            # Initialize active interface tracking so stale detection works on the second scrape
            # (if an interface disappears between first and second scrape, we need to know
            # what interfaces existed during the first scrape)
            self._active_internet_ids = {str(k) for k in netdev_info.internet.keys()} if netdev_info.internet else set()
            self._active_wireless_ids = {str(k) for k in netdev_info.wireless.keys()} if netdev_info.wireless else set()
            logger.debug("[%s] Network samples initialized (first collection)", product_id)
            return

        # Bridge metrics
        self._collect_simple_interface("bridge", product_id, netdev_info.bridge, self._bridge_tx, self._bridge_rx)

        # Wired metrics
        self._collect_simple_interface("wired", product_id, netdev_info.wired, self._wired_tx, self._wired_rx)

        # Internet metrics (multiple interfaces)
        current_internet_ids = {str(k) for k in netdev_info.internet.keys()} if netdev_info.internet else set()
        self._collect_multi_interface(
            "internet", product_id, netdev_info.internet, self._internet_tx, self._internet_rx
        )
        # Remove stale internet interface metrics
        self._remove_stale_interface_metrics(
            product_id, self._active_internet_ids, current_internet_ids, self._internet_tx, self._internet_rx
        )
        self._active_internet_ids = current_internet_ids

        # Wireless metrics (multiple interfaces)
        current_wireless_ids = {str(k) for k in netdev_info.wireless.keys()} if netdev_info.wireless else set()
        self._collect_multi_interface(
            "wireless", product_id, netdev_info.wireless, self._wireless_tx, self._wireless_rx
        )
        # Remove stale wireless interface metrics
        self._remove_stale_interface_metrics(
            product_id, self._active_wireless_ids, current_wireless_ids, self._wireless_tx, self._wireless_rx
        )
        self._active_wireless_ids = current_wireless_ids

        # Update previous samples
        self._previous_samples = self._create_network_samples(netdev_info)

        logger.debug(
            "[%s] Network metrics collected: internet=%d, wireless=%d",
            product_id,
            len(netdev_info.internet) if netdev_info.internet else 0,
            len(netdev_info.wireless) if netdev_info.wireless else 0,
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
        self, iface_type: str, product_id: str, current: Any, tx_counter: Counter, rx_counter: Counter
    ) -> None:
        """Collect metrics for a simple interface (no interface_id)."""
        prev = self._previous_samples.get(iface_type, {})

        if current is None:
            return

        tx = getattr(current, "total_upload_bytes", 0)
        rx = getattr(current, "total_download_bytes", 0)

        prev_tx = prev.get("tx", 0)
        prev_rx = prev.get("rx", 0)

        delta_tx = self._calculate_delta(tx, prev_tx)
        delta_rx = self._calculate_delta(rx, prev_rx)

        # Always call inc() to ensure consistent data points for rate() calculation
        tx_counter.labels(product_id=product_id).inc(delta_tx)
        rx_counter.labels(product_id=product_id).inc(delta_rx)

    def _collect_multi_interface(
        self, iface_type: str, product_id: str, interfaces: dict, tx_counter: Counter, rx_counter: Counter
    ) -> None:
        """Collect metrics for interfaces with interface_id label."""
        if not interfaces:
            return

        prev_interfaces: dict[str, dict[str, int]] = self._previous_samples.get(iface_type, {})  # type: ignore[assignment]

        for iface_id, current in interfaces.items():
            prev: dict[str, int] = prev_interfaces.get(str(iface_id), {})

            tx = getattr(current, "total_upload_bytes", 0)
            rx = getattr(current, "total_download_bytes", 0)

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
                "tx": getattr(netdev_info.bridge, "total_upload_bytes", 0),
                "rx": getattr(netdev_info.bridge, "total_download_bytes", 0),
            }

        if netdev_info.wired:
            samples["wired"] = {
                "tx": getattr(netdev_info.wired, "total_upload_bytes", 0),
                "rx": getattr(netdev_info.wired, "total_download_bytes", 0),
            }

        if netdev_info.internet:
            samples["internet"] = {}
            for iface_id, iface in netdev_info.internet.items():
                # Use str(iface_id) to match lookup in _collect_multi_interface
                samples["internet"][str(iface_id)] = {
                    "tx": getattr(iface, "total_upload_bytes", 0),
                    "rx": getattr(iface, "total_download_bytes", 0),
                }

        if netdev_info.wireless:
            samples["wireless"] = {}
            for iface_id, iface in netdev_info.wireless.items():
                # Use str(iface_id) to match lookup in _collect_multi_interface
                samples["wireless"][str(iface_id)] = {
                    "tx": getattr(iface, "total_upload_bytes", 0),
                    "rx": getattr(iface, "total_download_bytes", 0),
                }

        return samples

    @staticmethod
    def _calculate_delta(current: int, previous: int) -> int:
        """
        Calculate delta, handling counter wraps.

        Design Note on Counter Wrap Handling:
            When current < previous, the router's counter has wrapped (due to 32-bit
            overflow or router reboot). We return 0 rather than estimating the delta
            because:
            1. After reboot, the router may have accumulated some traffic before we
               read it, so using `current` as delta would be incorrect
            2. A single lost sample is preferable to incorrect data in rate() calculations
            3. Prometheus's rate() function handles gaps gracefully

            This may cause a brief dip in rate() graphs during counter wraps, but this
            is preferable to showing artificially inflated throughput.
        """
        if current >= previous:
            return current - previous
        # Counter wrapped - see design note above
        return 0

    def _remove_stale_interface_metrics(
        self,
        product_id: str,
        previous_ids: set[str],
        current_ids: set[str],
        tx_counter: Counter,
        rx_counter: Counter,
    ) -> None:
        """Remove metrics for interfaces that are no longer present.

        When network interfaces disappear (e.g., WAN failover, interface reconfiguration),
        their metrics would remain with stale values. This method removes those metrics
        to prevent confusion in dashboards and alerting.

        Uses prometheus_client's remove() method which is thread-safe and the proper API
        for removing specific label combinations.
        """
        stale_ids = previous_ids - current_ids
        for iface_id in stale_ids:
            # Use prometheus_client's remove() API which is thread-safe
            try:
                tx_counter.remove(product_id, iface_id)
            except KeyError:
                pass  # Label combination doesn't exist
            try:
                rx_counter.remove(product_id, iface_id)
            except KeyError:
                pass  # Label combination doesn't exist
            logger.debug("[%s] Removed stale metrics for interface %s", product_id, iface_id)

    def cleanup(self) -> None:
        """
        Clean up collector and reset state.

        Design Note on Counter Continuity:
            This method clears internal state but Prometheus Counter values are not reset
            (counters are monotonically increasing and cannot be decremented). When
            collection resumes after cleanup, the first collection re-initializes samples
            and subsequent collections continue accumulating from the existing counter
            values. This is the expected behavior for cleanup during shutdown - there will
            be a time gap in the metrics, but no data corruption. Prometheus's rate()
            function handles gaps gracefully.
        """
        super().cleanup()
        self._previous_samples.clear()
        self._active_internet_ids.clear()
        self._active_wireless_ids.clear()
