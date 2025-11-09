#!/usr/bin/env python3
"""
Prometheus exporter for ASUS router metrics.

This module exports various metrics from ASUS routers via Prometheus format.
It collects metrics like CPU usage, memory usage, temperature, uptime, and network throughput.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Iterable, Mapping

from prometheus_client import CollectorRegistry, Counter, Info, Gauge, Histogram, start_http_server

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
cpu_temp = Gauge(
    "asus_router_cpu_temperature_celsius",
    "CPU temperature in Celsius",
    ["product_id"],
    registry=registry,
)

cpu_usage_counter = Counter(
    "asus_router_cpu_usage",
    "Busy time (user+system+irq+...) in jiffies/ticks since boot",
    ["product_id", "cpu_id"],
    registry=registry,
)

cpu_total_counter = Counter(
    "asus_router_cpu_total",
    "Total time units (jiffies/ticks) elapsed since boot",
    ["product_id", "cpu_id"],
    registry=registry,
)

cpu_usage_percent_gauge = Gauge(
    "asus_router_cpu_usage_percent",
    "CPU usage percentage (Δusage / Δtotal * 100)",
    ["product_id", "cpu_id"],
    registry=registry,
)

memory_total_bytes = Gauge(
    "asus_router_memory_total_bytes",
    "Total memory in bytes",
    ["product_id"],
    registry=registry,
)

memory_used_bytes = Gauge(
    "asus_router_memory_used_bytes",
    "Used memory in bytes",
    ["product_id"],
    registry=registry,
)

memory_free_bytes = Gauge(
    "asus_router_memory_free_bytes",
    "Free memory in bytes",
    ["product_id"],
    registry=registry,
)

# опционально (удобно для панелей/алертов)
memory_used_percent = Gauge(
    "asus_router_memory_used_percent",
    "Memory usage percentage (used / total * 100)",
    ["product_id"],
    registry=registry,
)

bridge_tx_bytes = Counter(
    "asus_router_netdev_bridge_transmit_bytes_total",
    "Total bytes transmitted on bridge interface",
    ["product_id"],
    registry=registry,
)
bridge_rx_bytes = Counter(
    "asus_router_netdev_bridge_receive_bytes_total",
    "Total bytes received on bridge interface",
    ["product_id"],
    registry=registry,
)

wired_tx_bytes = Counter(
    "asus_router_netdev_wired_transmit_bytes_total",
    "Total bytes transmitted on wired interface",
    ["product_id"],
    registry=registry,
)
wired_rx_bytes = Counter(
    "asus_router_netdev_wired_receive_bytes_total",
    "Total bytes received on wired interface",
    ["product_id"],
    registry=registry,
)

internet_tx_bytes = Counter(
    "asus_router_netdev_internet_transmit_bytes_total",
    "Total bytes transmitted on internet interface",
    ["product_id", "interface_id"],
    registry=registry,
)
internet_rx_bytes = Counter(
    "asus_router_netdev_internet_receive_bytes_total",
    "Total bytes received on internet interface",
    ["product_id", "interface_id"],
    registry=registry,
)

wireless_tx_bytes = Counter(
    "asus_router_netdev_wireless_transmit_bytes_total",
    "Total bytes transmitted on wireless interface",
    ["product_id", "interface_id"],
    registry=registry,
)
wireless_rx_bytes = Counter(
    "asus_router_netdev_wireless_receive_bytes_total",
    "Total bytes received on wireless interface",
    ["product_id", "interface_id"],
    registry=registry,
)

router_info = Info(
    "asus_router_info",
    "Router information (static details such as product ID, model, firmware)",
    registry=registry,
)

# Uptime metrics
uptime_seconds = Gauge(
    "asus_router_uptime_seconds",
    "Router uptime in seconds",
    ["product_id"],
    registry=registry,
)

# Until next reboot metrics
next_reboot_seconds = Gauge(
    "asus_router_reboot_schedule_second_until_next",
    "Seconds until next scheduled reboot",
    ["product_id"],
    registry=registry,
)

router_mode = Gauge(
    "asus_router_sw_mode",
    "Asus router mode (one-hot)",
    ["product_id", "sw_mode"],
    registry=registry,
)

wans = {
    "dualwan_enabled": Gauge(
        "asus_router_dualwan_enabled",
        "Dual WAN enabled",
        ["product_id"],
        registry=registry
    ),
    "dualwan_mode": Gauge(
        "asus_router_dualwan_mode",
        "Dual WAN mode (one-hot)",
        ["product_id", "mode"],
        registry=registry
    ),
    "link_internet": Gauge(
        "asus_router_link_internet_status",
        "Link internet status (0/1)",
        ["product_id"],
        registry=registry
    ),
    "wan_auxstate": Gauge(
        "asus_router_wan_connection_auxstate",
        "WAN cable/aux state (one-hot)",
        ["product_id", "unit", "auxstate"],
        registry=registry
    ),
    "wan_state": Gauge(
        "asus_router_wan_connection_state",
        "WAN state (one-hot)",
        ["product_id", "unit", "state"],
        registry=registry
    ),
    "wan_substate": Gauge(
        "asus_router_wan_connection_substate",
        "WAN substate (one-hot)",
        ["product_id", "unit", "substate"],
        registry=registry
    ),
    "wan_online": Gauge(
        "asus_router_wan_connection_online",
        "WAN online status (0/1)",
        ["product_id", "unit"],
        registry=registry
    ),
    "wan_status": Gauge(
        "asus_router_wan_status", "WAN status (one-hot)",
        ["product_id", "unit", "status"],
        registry=registry
    ),
    "wan_active": Gauge(
        "asus_router_wan_active",
        "WAN active (0/1)",
        ["product_id", "unit"],
        registry=registry
    ),
}

wireless = {
    "wl_wps_enabled": Gauge(
        "asus_router_wireless_wps_enabled",
        "Wireless WPS enabled",
        ["product_id"],
        registry=registry
    ),
    "wl_smart_connect_enabled": Gauge(
        "asus_router_wireless_smart_connect_enabled",
        "Wireless Smart Connect enabled",
        ["product_id"],
        registry=registry
    ),
    "wl_band_info": Info(
        "asus_router_wireless_band",
        "Wireless Band info",
["product_id", "wl_unit"],
        registry=registry
    ),
    "wl_band_mode": Gauge(
        "asus_router_wireless_band_mode",
        "Wireless Band mode (one-hot)",
        ["product_id", "wl_unit", "wl_mode"],
        registry=registry
    ),
    "wl_auth_mode": Gauge(
        "asus_router_wireless_auth_mode",
        "Wireless Auth mode (one-hot)",
        ["product_id", "wl_unit", "wl_auth_mode"],
        registry=registry
    ),
    "wl_crypto": Gauge(
        "asus_router_wireless_crypto",
        "Wireless Crypto (one-hot)",
        ["product_id", "wl_unit", "wl_crypto"],
        registry=registry
    ),
    "wl_ssid_hidden": Gauge(
        "asus_router_wireless_ssid_hidden",
        "Wireless SSID (0, 1)",
        ["product_id", "wl_unit"],
        registry=registry
    )
}

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

def _b(v: bool | int) -> int:
    """bool/int → 0/1"""
    return 1 if bool(v) else 0

def set_onehot_enum(
    gauge: Gauge,
    base_labels: Mapping[str, str],
    enum_values: Iterable,
    current_value,
    extra_label_name: str,
    get_label_value=lambda e: getattr(e, "value", getattr(e, "name", str(e))),
):
    for e in enum_values:
        labels = dict(base_labels)
        labels[extra_label_name] = get_label_value(e)
        gauge.labels(**labels).set(1 if e == current_value else 0)

def zero_onehot_enum(
    gauge: Gauge,
    base_labels: Mapping[str, str],
    enum_values: Iterable,
    extra_label_name: str,
    get_label_value=lambda e: getattr(e, "value", getattr(e, "name", str(e))),
):
    for e in enum_values:
        labels = dict(base_labels)
        labels[extra_label_name] = get_label_value(e)
        gauge.labels(**labels).set(0)

def _inc_if_positive(counter_child, delta: int):
    if delta > 0:
        counter_child.inc(delta)

class _CpuMetricChildren:
    def __init__(self):
        self.temp: Dict[str, any] = {}
        self.usage: Dict[Tuple[str, str], any] = {}
        self.total: Dict[Tuple[str, str], any] = {}
        self.percent: Dict[Tuple[str, str], any] = {}

    def temp_child(self, product_id: str):
        c = self.temp.get(product_id)
        if c is None:
            c = cpu_temp.labels(product_id=product_id)
            self.temp[product_id] = c
        return c

    def usage_child(self, product_id: str, cpu_id: str):
        key = (product_id, cpu_id)
        c = self.usage.get(key)
        if c is None:
            c = cpu_usage_counter.labels(product_id=product_id, cpu_id=cpu_id)
            self.usage[key] = c
        return c

    def total_child(self, product_id: str, cpu_id: str):
        key = (product_id, cpu_id)
        c = self.total.get(key)
        if c is None:
            c = cpu_total_counter.labels(product_id=product_id, cpu_id=cpu_id)
            self.total[key] = c
        return c

    def percent_child(self, product_id: str, cpu_id: str):
        key = (product_id, cpu_id)
        c = self.percent.get(key)
        if c is None:
            c = cpu_usage_percent_gauge.labels(product_id=product_id, cpu_id=cpu_id)
            self.percent[key] = c
        return c

class _MemMetricChildren:
    def __init__(self):
        self.total = {}
        self.used = {}
        self.free = {}
        self.used_pct = {}

    def for_pid(self, pid: str):
        # возврат подготовленных childs для данного product_id
        total = self.total.get(pid)
        if total is None:
            total = memory_total_bytes.labels(product_id=pid); self.total[pid] = total
        used = self.used.get(pid)
        if used is None:
            used = memory_used_bytes.labels(product_id=pid); self.used[pid] = used
        free = self.free.get(pid)
        if free is None:
            free = memory_free_bytes.labels(product_id=pid); self.free[pid] = free
        used_pct = self.used_pct.get(pid)
        if used_pct is None:
            used_pct = memory_used_percent.labels(product_id=pid); self.used_pct[pid] = used_pct
        return total, used, free, used_pct

class RouterMetricsCollector:
    """Collects metrics from ASUS router and updates Prometheus metrics."""

    def __init__(self, client: asus_router_client.RouterClient):
        self.client = client
        self._cpu_children = _CpuMetricChildren()
        self._mem_children = _MemMetricChildren()
        self.router_info: asus_router_client.RouterInfo | None = None
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

    def _get_base_labels(self, **extra_labels) -> Dict[str, str]:
        """
        Get base labels dict with product_id and any extra labels.

        Args:
            **extra_labels: Additional labels to include (e.g., unit, interface_id)

        Returns:
            Dict with product_id and extra labels
        """
        labels = {"product_id": self.router_info.product_id}
        labels.update(extra_labels)
        return labels

    @staticmethod
    def _kb_to_bytes(kb: int | float | None) -> float | None:
        if kb is None:
            return None
        try:
            return float(kb) * 1024.0
        except Exception:
            return None

    @staticmethod
    def _calculate_delta(current: int, previous: int) -> int:
        """
        Robust delta between two cumulative counters.
        - Never returns negative.
        """
        if current >= previous:
            return current - previous

        return 0

    @staticmethod
    def _create_network_samples(netdev_info: asus_router_client.NetdevInfo) -> dict:
        """
        Prepare snapshot of current counters for delta math on next scrape.
        """
        return {
            "bridge": ThroughputSample(
                tx=netdev_info.bridge.total_upload_bytes,
                rx=netdev_info.bridge.total_download_bytes,
            ),
            "wired": ThroughputSample(
                tx=netdev_info.wired.total_upload_bytes,
                rx=netdev_info.wired.total_download_bytes,
            ),
            "internet": {
                iid: ThroughputSample(
                    tx=th.total_upload_bytes,
                    rx=th.total_download_bytes,
                ) for iid, th in netdev_info.internet.items()
            },
            "wireless": {
                wid: ThroughputSample(
                    tx=th.total_upload_bytes,
                    rx=th.total_download_bytes,
                ) for wid, th in netdev_info.wireless.items()
            },
        }

    def _collect_simple_interface_metrics(self, interface_type: str, current_throughput,
                                          prev_throughput, tx_counter, rx_counter) -> None:
        """
        Update metrics for simple interfaces with no sub-interfaces (bridge, wired).

        Args:
            interface_type: Type of interface ("bridge" or "wired")
            current_throughput: Current interface throughput data
            prev_throughput: Previous throughput sample (ThroughputSample)
            tx_counter: Prometheus counter for transmit bytes
            rx_counter: Prometheus counter for receive bytes
        """
        base_labels = self._get_base_labels()
        delta_tx = self._calculate_delta(current_throughput.total_upload_bytes, prev_throughput.tx)
        delta_rx = self._calculate_delta(current_throughput.total_download_bytes, prev_throughput.rx)
        tx_counter.labels(**base_labels).inc(delta_tx)
        rx_counter.labels(**base_labels).inc(delta_rx)
        logger.debug(f"[{base_labels['product_id']}] {interface_type.capitalize()}: tx Δ={delta_tx}, rx Δ={delta_rx}")

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
        base_labels = self._get_base_labels()
        for interface_id, throughput in interfaces.items():
            labels = self._get_base_labels(interface_id=str(interface_id))
            if interface_id in prev_interfaces:
                prev_iface = prev_interfaces[interface_id]
                delta_tx = self._calculate_delta(throughput.total_upload_bytes, prev_iface.tx)
                delta_rx = self._calculate_delta(throughput.total_download_bytes, prev_iface.rx)
            else:
                logger.debug(f"[{base_labels['product_id']}] {interface_type.capitalize()} interface {interface_id} - first sample, storing baseline")
                delta_tx = 0
                delta_rx = 0

            tx_counter.labels(**labels).inc(delta_tx)
            rx_counter.labels(**labels).inc(delta_rx)
            logger.debug(f"[{base_labels['product_id']}] {interface_type.capitalize()} {interface_id}: tx Δ={delta_tx}, rx Δ={delta_rx}")

    @staticmethod
    def _set_gauge_safe(child, value: float | None):
        """Set gauge value; if None/invalid -> NaN to avoid misleading zeroes."""
        try:
            child.set(float(value) if value is not None and not math.isnan(value) else float("nan"))
        except Exception as e:
            logger.warning(f"Failed to set gauge: {e}")

    def collect_all_metrics(self):
        """Collect all available metrics from the router."""
        with scrape_duration_seconds.time():
            try:
                # Collect product_id first as it's used in all metrics
                self._collect_router_info()

                if not self.router_info.product_id:
                    logger.warning("Product ID not available, skipping metric collection")
                    return

                self._collect_temperature_metrics()
                self._collect_cpu_metrics()
                self._collect_memory_metrics()
                self._collect_network_metrics()
                self._collect_wan_info_metrics()
                self._collect_wireless_metrics()
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                scrape_errors_total.inc()
                raise

    def _collect_wan_info_metrics(self):
        base_labels = self._get_base_labels()

        net_wan_info = self.client.get_network_wan_info()
        wans["link_internet"].labels(**base_labels).set(net_wan_info.has_internet)

        dual = net_wan_info.dual_wan_info
        if dual is not None:
            wans["dualwan_enabled"].labels(**base_labels).set(_b(dual.enabled))
            # one-hot по режимам
            set_onehot_enum(
                wans["dualwan_mode"],
                base_labels,
                asus_router_client.WanMode,
                dual.wans_mode,
                extra_label_name="mode",
                get_label_value=lambda e: e.value,  # "fo"/"fb"/"lb"
            )
        else:
            # не чистим серии, просто обнулим — стабильнее для прометея
            wans["dualwan_enabled"].labels(**base_labels).set(0)
            zero_onehot_enum(
                wans["dualwan_mode"],
                base_labels,
                asus_router_client.WanMode,
                extra_label_name="mode",
                get_label_value=lambda e: e.value,
            )

        # первичный/вторичный WAN
        self._collect_wan_metrics(0, net_wan_info.primary_wan)
        self._collect_wan_metrics(1, net_wan_info.secondary_wan)

    def _collect_wan_metrics(self, unit: int, wan_info: Optional[asus_router_client.WanInfo]):
        base_labels = self._get_base_labels(unit=str(unit))

        if wan_info is None:
            # WAN отсутствует: обнулить one-hot и простые gauge
            zero_onehot_enum(
                wans["wan_auxstate"], base_labels, asus_router_client.WanAuxState,
                extra_label_name="auxstate", get_label_value=lambda e: e.name
            )
            zero_onehot_enum(
                wans["wan_state"], base_labels, asus_router_client.WanState,
                extra_label_name="state", get_label_value=lambda e: e.name
            )
            zero_onehot_enum(
                wans["wan_substate"], base_labels, asus_router_client.WanSubState,
                extra_label_name="substate", get_label_value=lambda e: e.name
            )
            zero_onehot_enum(
                wans["wan_status"], base_labels, asus_router_client.WanStatus,
                extra_label_name="status", get_label_value=lambda e: e.value
            )
            wans["wan_online"].labels(**base_labels).set(0)
            wans["wan_active"].labels(**base_labels).set(0)
            return

        conn = wan_info.connection_info

        # one-hot по enum'ам
        set_onehot_enum(
            wans["wan_auxstate"], base_labels, asus_router_client.WanAuxState,
            conn.auxstate, extra_label_name="auxstate", get_label_value=lambda e: e.name
        )
        set_onehot_enum(
            wans["wan_state"], base_labels, asus_router_client.WanState,
            conn.state, extra_label_name="state", get_label_value=lambda e: e.name
        )
        set_onehot_enum(
            wans["wan_substate"], base_labels, asus_router_client.WanSubState,
            conn.substate, extra_label_name="substate", get_label_value=lambda e: e.name
        )

        wans["wan_online"].labels(**base_labels).set(_b(conn.is_connected))

        set_onehot_enum(
            wans["wan_status"], base_labels, asus_router_client.WanStatus,
            wan_info.status, extra_label_name="status", get_label_value=lambda e: e.value
        )

        wans["wan_active"].labels(**base_labels).set(_b(wan_info.active))

    def _collect_temperature_metrics(self):
        """Collect temperature metrics with logging and safety."""
        pid = self.router_info.product_id
        child = self._cpu_children.temp_child(pid)
        try:
            temp_info = self.client.get_core_temp()
            self._set_gauge_safe(child, temp_info.cpu)
            logger.debug(f"[{pid}] CPU temperature: {temp_info.cpu:.1f}°C")
        except Exception as e:
            logger.warning(f"[{pid}] CPU temperature collection failed: {e}")
            self._set_gauge_safe(child, None)

    def _collect_cpu_metrics(self):
        """Collect CPU usage metrics."""
        """
            Export:
              - asus_router_cpu_usage / asus_router_cpu_total : Counter (inc by deltas)
              - asus_router_cpu_usage_percent : Gauge computed from deltas
            Resilient to wraps/resets; clamps percent to [0, 100].
            """
        pid = self.router_info.product_id
        try:
            cpu_infos = self.client.get_cpu_usage()
        except Exception as e:
            logger.warning(f"[{pid}] CPU usage collection failed: {e}")
            return

        for i, cpu_info in enumerate(cpu_infos):
            cpu_id = str(i)

            # store current sample
            prev = self.previous_cpu_samples.get(cpu_id)

            # on subsequent scrapes: compute deltas
            if prev is not None:
                du = self._calculate_delta(cpu_info.usage, prev["usage"])
                dt = self._calculate_delta(cpu_info.total, prev["total"])

                # update counters by deltas only (never set absolute values on Counter)
                self._cpu_children.usage_child(pid, cpu_id).inc(max(0, du))
                self._cpu_children.total_child(pid, cpu_id).inc(max(0, dt))

                if dt > 0:
                    pct = max(0.0, min(100.0, (du / dt) * 100.0))
                    self._cpu_children.percent_child(pid, cpu_id).set(pct)
                    logger.debug(f"[{pid}] CPU {cpu_id}: usage Δ={du}, total Δ={dt}, {pct:.1f}%")
                else:
                    # dt == 0 (no progress / error): set NaN to indicate unknown
                    self._cpu_children.percent_child(pid, cpu_id).set(float("nan"))
            else:
                # first sample: cannot compute deltas yet → set percent NaN
                self._cpu_children.percent_child(pid, cpu_id).set(float("nan"))

            self.previous_cpu_samples[cpu_id] = {"usage": cpu_info.usage, "total": cpu_info.total}

        logger.debug(f"[{pid}] CPU metrics collected: {len(cpu_infos)} CPUs")

    def _collect_memory_metrics(self):
        """Collect memory usage metrics (KB from router -> bytes)."""
        pid = self.router_info.product_id
        total_c, used_c, free_c, used_pct_c = self._mem_children.for_pid(pid)

        try:
            mem = self.client.get_memory_usage()  # ожидается .total_kb / .used_kb / .free_kb
            total_b = self._kb_to_bytes(mem.total_kb)
            used_b = self._kb_to_bytes(mem.used_kb)
            free_b = self._kb_to_bytes(mem.free_kb)

            self._set_gauge_safe(total_c, total_b)
            self._set_gauge_safe(used_c, used_b)
            self._set_gauge_safe(free_c, free_b)

            # процент, если можем посчитать
            if total_b and total_b > 0 and used_b is not None:
                pct = max(0.0, min(100.0, (used_b / total_b) * 100.0))
                self._set_gauge_safe(used_pct_c, pct)
            else:
                self._set_gauge_safe(used_pct_c, None)

            logger.debug(f"[{pid}] Memory: total={mem.total_kb}KB, used={mem.used_kb}KB, free={mem.free_kb}KB")

        except Exception as e:
            logger.warning(f"[{pid}] Memory collection failed: {e}")
            # выставим NaN, чтобы явно показать отсутствие данных
            self._set_gauge_safe(total_c, None)
            self._set_gauge_safe(used_c, None)
            self._set_gauge_safe(free_c, None)
            self._set_gauge_safe(used_pct_c, None)

    def _collect_network_metrics(self):
        """Collect network throughput metrics.

        Export:
          - Network interface counters (bridge, wired, internet, wireless) via tx/rx bytes
          - Resilient to wraps/resets; increments by deltas only
        """
        pid = self.router_info.product_id
        try:
            netdev_info = self.client.get_netdev()
        except Exception as e:
            logger.warning(f"[{pid}] Network collection failed: {e}")
            return

        # Initialize network samples tracking if not present
        if not self.previous_network_samples:
            self.previous_network_samples = self._create_network_samples(netdev_info)
            logger.debug(f"[{pid}] Network samples initialized (first collection)")
            return

        # Bridge metrics
        self._collect_simple_interface_metrics(
            "bridge", netdev_info.bridge,
            self.previous_network_samples["bridge"],
            bridge_tx_bytes, bridge_rx_bytes
        )

        # Wired metrics
        self._collect_simple_interface_metrics(
            "wired", netdev_info.wired,
            self.previous_network_samples["wired"],
            wired_tx_bytes, wired_rx_bytes
        )

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
            f"[{pid}] Network metrics collected: "
            f"internet={len(netdev_info.internet)}, "
            f"wireless={len(netdev_info.wireless)}"
        )

    def _collect_wireless_metrics(self):
        base_labels = self._get_base_labels()
        wireless_info = self.client.get_wireless_info()
        wireless["wl_wps_enabled"].labels(**base_labels).set(_b(wireless_info.wps_enabled))
        wireless["wl_smart_connect_enabled"].labels(**base_labels).set(_b(wireless_info.smart_connect_enabled))

        self._collect_wileless_band_metrics(asus_router_client.WifiUnit.WL_2G, wireless_info.band_2G_info)
        self._collect_wileless_band_metrics(asus_router_client.WifiUnit.WL_5G, wireless_info.band_5G_info)
        self._collect_wileless_band_metrics(asus_router_client.WifiUnit.WL_5G_2, wireless_info.band_5G_2_info)
        self._collect_wileless_band_metrics(asus_router_client.WifiUnit.WL_6G, wireless_info.band_6G_info)

    def _collect_wileless_band_metrics(self, wl_unit: asus_router_client.WifiUnit, wl_unit_info: asus_router_client.WifiBandInfo):
        if wl_unit_info is None:
            return

        base_labels = self._get_base_labels(wl_unit=str(wl_unit.value))
        wireless["wl_band_info"].labels(**base_labels).info({
            "wl_ssid": wl_unit_info.ssid,
            "wl_mac": wl_unit_info.mac,
        })

        wireless["wl_ssid_hidden"].labels(**base_labels).set(_b(wl_unit_info.hidde_ssid))

        set_onehot_enum(
            wireless["wl_band_mode"],
            base_labels,
            asus_router_client.WifiMode,
            wl_unit_info.mode,
            extra_label_name="wl_mode",
            get_label_value = lambda e: e.name
        )

        set_onehot_enum(
            wireless["wl_auth_mode"],
            base_labels,
            asus_router_client.WifiAuthMode,
            wl_unit_info.auth_mode,
            extra_label_name="wl_auth_mode",
            get_label_value=lambda e: e.value
        )

        set_onehot_enum(
            wireless["wl_crypto"],
            base_labels,
            asus_router_client.WifiCrypto,
            wl_unit_info.crypto,
            extra_label_name="wl_crypto",
            get_label_value=lambda e: e.value
        )

    def _collect_router_info(self):
        """Collect router static info and uptime metrics."""
        info = self.client.get_info()
        self.router_info = info  # store locally for reuse
        base_labels = self._get_base_labels()

        # --- Static info ---
        # Assuming info contains fields like product_id, model, fw_version, etc.
        router_info.info({
            "product_id": info.product_id,
            "firmware": f"{info.firmver}_{info.extendno}",
            "serial": info.serial_no,
            "hostname": info.lan_hostname,
            "mac": info.lan_hwaddr
        })

        # --- Uptime ---
        uptime_seconds.labels(**base_labels).set(info.uptime.boottime)

        # --- SW Mode ---
        set_onehot_enum(
            router_mode, base_labels, asus_router_client.SwMode,
            info.sw_mode, extra_label_name="sw_mode", get_label_value=lambda e: e.name
        )

        # --- Next reboot ---
        reboot_schedule = info.reboot_schedule
        if reboot_schedule and reboot_schedule.until_ms is not None:
            next_reboot_seconds.labels(**base_labels).set(reboot_schedule.until_ms / 1000)
            logger.debug(f"[{base_labels['product_id']}] Reboot schedule in {reboot_schedule.until_ms / 1000:.0f}s")
        else:
            next_reboot_seconds.labels(**base_labels).set(float("nan"))

        logger.debug(f"[{base_labels['product_id']}] Router info collected successfully")


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
