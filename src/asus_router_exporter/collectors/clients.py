"""
Client metrics collector.

Collects metrics for connected clients:
- Client information
- Connection status
- Signal strength
- Traffic statistics
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import CollectorRegistry, Gauge, Info

from ..client import models as client_models
from ..client.models import ClientInfo, ClientInterface
from ..core.protocols import ConfigProviderProtocol, RouterClientProtocol
from .base import BaseCollector, LabeledMetricsMixin

logger = logging.getLogger(__name__)


class ClientsCollector(LabeledMetricsMixin, BaseCollector):
    """
    Collector for client metrics.

    Design Note on Metric Clearing:
        This collector clears all metrics at the start of each collection cycle.
        While this breaks Prometheus time series continuity, it's necessary because:

        1. Client label values are mutable - clients can roam between AIMesh nodes
           (changing client_amesh_pap_mac), switch interfaces (changing
           client_conn_interface), or have their names updated (changing client_name).

        2. Without clearing, the same physical device would accumulate multiple
           metric series with different label combinations, causing data inconsistency
           and metric explosion.

        3. The LabeledMetricsMixin is inherited but not fully utilized because tracking
           by MAC alone doesn't solve the mutable-labels problem. A client staying
           connected but changing interfaces would still leave stale metrics.

        Future improvement: Refactor to use MAC as primary identifier with mutable
        attributes as Info metric values rather than labels. This would allow proper
        time series continuity while avoiding stale data.

    Metrics:
    - asus_router_client_info (Info)
    - asus_router_client_operation_mode (one-hot)
    - asus_router_client_ip_method (one-hot)
    - asus_router_client_interface (one-hot)
    - asus_router_client_online (0/1)
    - asus_router_client_last_conn_timestamp
    - asus_router_client_conn_duration_seconds
    - asus_router_client_internet_mode (one-hot)
    - asus_router_client_internet_state (0/1)
    - asus_router_client_rssi_dbm
    - asus_router_client_rssi_strength (one-hot)
    - asus_router_client_netdev_rx_bytes
    - asus_router_client_netdev_tx_bytes
    - asus_router_client_netdev_rx_throughput_bps
    - asus_router_client_netdev_tx_throughput_bps
    - asus_router_client_amesh_role (one-hot)
    """

    name = "clients"

    # Common client labels
    # Design Note on client_name label:
    # Including client_name in labels could theoretically cause cardinality issues if users
    # frequently rename devices. However, this is mitigated because:
    # 1. Metrics are cleared at the start of each collection cycle (see _collect_metrics)
    # 2. The number of connected clients is typically small (< 100 for home routers)
    # 3. The client_name provides valuable context for dashboards and alerting
    # 4. The alternative (Info metric only) would make it hard to correlate with other metrics
    CLIENT_LABELS = ["product_id", "client_mac", "client_conn_interface", "client_amesh_pap_mac", "client_name"]

    def __init__(
        self,
        registry: CollectorRegistry,
        config: ConfigProviderProtocol,
    ):
        LabeledMetricsMixin.__init__(self)
        BaseCollector.__init__(self, registry, config)

    def _create_metrics(self) -> None:
        """Create client metrics."""
        self._client_info = Info(
            "asus_router_client_info",
            "Basic client metadata",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._client_info)

        self._op_mode = Gauge(
            "asus_router_client_operation_mode",
            "Client operation mode (one-hot)",
            self.CLIENT_LABELS + ["client_op_mode"],
            registry=self._registry,
        )
        self._register_metric(self._op_mode)

        self._ip_method = Gauge(
            "asus_router_client_ip_method",
            "Client IP assignment method (one-hot)",
            self.CLIENT_LABELS + ["client_ip_method"],
            registry=self._registry,
        )
        self._register_metric(self._ip_method)

        self._interface = Gauge(
            "asus_router_client_interface",
            "Client connection interface (one-hot)",
            ["product_id", "client_mac", "client_amesh_pap_mac", "client_name", "client_conn_interface"],
            registry=self._registry,
        )
        self._register_metric(self._interface)

        self._online = Gauge(
            "asus_router_client_online",
            "Client online status (1=online, 0=offline)",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._online)

        self._last_conn_ts = Gauge(
            "asus_router_client_last_conn_timestamp",
            "Last connection UNIX timestamp reported by router",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._last_conn_ts)

        self._conn_duration = Gauge(
            "asus_router_client_conn_duration_seconds",
            "Current connection duration in seconds derived from conn_ts",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._conn_duration)

        self._internet_mode = Gauge(
            "asus_router_client_internet_mode",
            "Client internet mode (one-hot)",
            self.CLIENT_LABELS + ["client_internet_mode"],
            registry=self._registry,
        )
        self._register_metric(self._internet_mode)

        self._internet_state = Gauge(
            "asus_router_client_internet_state",
            "Client internet state (0/1)",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._internet_state)

        self._rssi_dbm = Gauge(
            "asus_router_client_rssi_dbm",
            "Client RSSI signal strength in dBm",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._rssi_dbm)

        self._rssi_strength = Gauge(
            "asus_router_client_rssi_strength",
            "Client RSSI strength (one-hot)",
            self.CLIENT_LABELS + ["client_rssi_strength"],
            registry=self._registry,
        )
        self._register_metric(self._rssi_strength)

        # Note: These are Gauges (not Counters) because the router reports cumulative totals
        # that can reset when clients reconnect. Using "_bytes" without "_total" suffix
        # follows Prometheus naming conventions where "_total" indicates a monotonic counter.
        self._rx_bytes = Gauge(
            "asus_router_client_netdev_rx_bytes",
            "Cumulative received bytes per client as reported by router (resets on reconnect)",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._rx_bytes)

        self._tx_bytes = Gauge(
            "asus_router_client_netdev_tx_bytes",
            "Cumulative transmitted bytes per client as reported by router (resets on reconnect)",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._tx_bytes)

        self._rx_throughput = Gauge(
            "asus_router_client_netdev_rx_throughput_bps",
            "Current receive throughput in bits per second",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._rx_throughput)

        self._tx_throughput = Gauge(
            "asus_router_client_netdev_tx_throughput_bps",
            "Current transmit throughput in bits per second",
            self.CLIENT_LABELS,
            registry=self._registry,
        )
        self._register_metric(self._tx_throughput)

        self._amesh_role = Gauge(
            "asus_router_client_amesh_role",
            "AI Mesh role (one-hot)",
            self.CLIENT_LABELS + ["amesh_role"],
            registry=self._registry,
        )
        self._register_metric(self._amesh_role)

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect client metrics from router."""
        product_id = getattr(router_info, "product_id", "unknown")

        # Clear all metrics before collection to prevent stale data from clients
        # with changed labels. See class docstring "Design Note on Metric Clearing"
        # for detailed explanation of this design tradeoff.
        self._clear_metrics()

        try:
            client_list = router_client.get_clients()
        except Exception:
            logger.warning("[%s] Client collection failed", product_id, exc_info=True)
            return

        for client in client_list:
            self._collect_client_metrics(product_id, client)

        logger.debug("[%s] Client metrics collected: %d clients", product_id, len(client_list))

    def _collect_client_metrics(self, product_id: str, client: Any) -> None:
        """Collect metrics for a single client."""
        # Determine interface based on client type
        if isinstance(client, ClientInfo):
            interface = getattr(client, "interface", None)
            ipaddr = getattr(client, "ipaddr", "")
        else:
            interface = getattr(client, "last_conn_interface", None)
            ipaddr = ""

        # Get interface label
        interface_label = interface.label if interface and hasattr(interface, "label") else "unknown"

        # Get amesh info
        amesh_info = getattr(client, "amesh_info", None)
        amesh_pap_mac = getattr(amesh_info, "pap_mac", "") if amesh_info else ""

        # Get client name (prefer nick_name, then name, then vendor)
        nick_name = getattr(client, "nick_name", "") or ""
        name = getattr(client, "name", "") or ""
        vendor = getattr(client, "vendor", "") or ""
        client_name = next((s for s in [nick_name, name, vendor] if s.strip()), "unknown")

        # Build labels
        labels = {
            "product_id": product_id,
            "client_mac": getattr(client, "mac", ""),
            "client_conn_interface": interface_label,
            "client_amesh_pap_mac": amesh_pap_mac,
            "client_name": client_name,
        }

        # Client info
        self._client_info.labels(**labels).info(
            {
                "ipaddr": ipaddr,
                "name": name,
                "nick_name": nick_name,
                "vendor": vendor,
            }
        )

        # For full ClientInfo, collect detailed metrics
        if isinstance(client, ClientInfo):
            self._collect_detailed_client_metrics(client, labels, interface)

    def _collect_detailed_client_metrics(self, client: Any, labels: dict, interface: Any) -> None:
        """Collect detailed metrics for connected clients."""
        # Operation mode (one-hot)
        op_mode = getattr(client, "op_mode", None)
        self._set_onehot_enum(self._op_mode, labels, op_mode, "client_op_mode", "ClientOperationMode", lambda e: e.name)

        # IP method (one-hot)
        ip_method = getattr(client, "ip_method", None)
        self._set_onehot_enum(
            self._ip_method, labels, ip_method, "client_ip_method", "ClientIpMethod", lambda e: e.value
        )

        # Interface (one-hot) - different label structure
        interface_labels = {k: v for k, v in labels.items() if k != "client_conn_interface"}
        self._set_onehot_interface(interface_labels, interface)

        # Online status
        online = getattr(client, "online", False)
        self._online.labels(**labels).set(1 if online else 0)

        # Last connection timestamp
        last_conn_ts = getattr(client, "last_conn_ts", None)
        if last_conn_ts is not None:
            self._last_conn_ts.labels(**labels).set(last_conn_ts)
        else:
            self._last_conn_ts.labels(**labels).set(float("nan"))

        # Connection duration
        conn_ts = getattr(client, "conn_ts", None)
        if conn_ts is not None:
            self._conn_duration.labels(**labels).set(conn_ts)
        else:
            self._conn_duration.labels(**labels).set(float("nan"))

        # Internet mode (one-hot)
        internet_mode = getattr(client, "internet_mode", None)
        self._set_onehot_enum(
            self._internet_mode, labels, internet_mode, "client_internet_mode", "ClientInternetMode", lambda e: e.value
        )

        # Internet state
        internet_state = getattr(client, "internet_state", None)
        if internet_state is not None:
            state_val = internet_state.value if hasattr(internet_state, "value") else internet_state
            self._internet_state.labels(**labels).set(1 if state_val else 0)

        # RSSI - only emit for wireless clients (wired clients have no RSSI)
        # Skip RSSI metrics entirely for wired (LAN) clients to avoid polluting
        # metrics with meaningless NaN values.
        is_wireless = interface is not None and interface != ClientInterface.LAN
        if is_wireless:
            rssi = getattr(client, "rssi", None)
            if rssi is not None:
                self._rssi_dbm.labels(**labels).set(rssi)
            else:
                self._rssi_dbm.labels(**labels).set(float("nan"))

            # RSSI strength (one-hot)
            rssi_strength = getattr(client, "rssi_strength", None)
            self._set_onehot_enum(
                self._rssi_strength, labels, rssi_strength, "client_rssi_strength", "RssiStrength", lambda e: e.name
            )

        # Traffic statistics (instantaneous throughput values)
        traffic_stats = getattr(client, "traffic_stats", None)
        if traffic_stats:
            rx = getattr(traffic_stats, "rx", 0) or 0
            tx = getattr(traffic_stats, "tx", 0) or 0
            self._rx_throughput.labels(**labels).set(rx)
            self._tx_throughput.labels(**labels).set(tx)

        # Throughput info (cumulative byte totals)
        throughput_info = getattr(client, "throughput_info", None)
        if throughput_info:
            rx_bytes = getattr(throughput_info, "total_download_bytes", 0) or 0
            tx_bytes = getattr(throughput_info, "total_upload_bytes", 0) or 0
            self._rx_bytes.labels(**labels).set(rx_bytes)
            self._tx_bytes.labels(**labels).set(tx_bytes)

        # A-Mesh role (one-hot)
        amesh_info = getattr(client, "amesh_info", None)
        amesh_role = getattr(amesh_info, "role", None) if amesh_info else None
        self._set_onehot_enum(self._amesh_role, labels, amesh_role, "amesh_role", "ClientAmeshRole", lambda e: e.value)

    def _set_onehot_interface(self, labels: dict, current_interface: Any) -> None:
        """Set one-hot encoding for client interface."""
        for iface in ClientInterface:
            value = 1 if iface == current_interface else 0
            self._interface.labels(**labels, client_conn_interface=iface.label).set(value)

    def _set_onehot_enum(
        self, gauge: Gauge, labels: dict, current_value: Any, label_name: str, enum_name: str, get_label_value: Any
    ) -> None:
        """Set one-hot encoding for an enum value."""
        try:
            enum_class = getattr(client_models, enum_name, None)
            if enum_class and current_value is not None:
                for enum_val in enum_class:
                    value = 1 if enum_val == current_value else 0
                    gauge.labels(**labels, **{label_name: get_label_value(enum_val)}).set(value)
            elif enum_class:
                # Set all to 0 when current_value is None
                for enum_val in enum_class:
                    gauge.labels(**labels, **{label_name: get_label_value(enum_val)}).set(0)
        except (ImportError, AttributeError):
            if current_value is not None:
                gauge.labels(**labels, **{label_name: str(current_value)}).set(1)

    def reset_state(self) -> None:
        """Reset internal state on node switch.

        Clears active labels tracking to prevent stale label detection
        issues when switching between AiMesh nodes.
        """
        self._active_labels.clear()
        logger.debug("[%s] Clients collector state reset", self.name)

    def cleanup(self) -> None:
        """Clean up collector and reset state."""
        super().cleanup()
        # Clear mixin state from LabeledMetricsMixin
        self._active_labels.clear()
