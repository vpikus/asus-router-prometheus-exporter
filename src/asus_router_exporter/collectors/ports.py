"""
Ports metrics collector.

Collects:
- Port connection status
- Port link rates
- Port groups
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import Gauge, Info

from ..client.models import PortGroup
from ..core.protocols import RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class PortsCollector(BaseCollector):
    """
    Collector for port metrics.

    Metrics:
    - asus_router_ports_plugged: Port connection status (0/1)
    - asus_router_ports_link_rate_mbps: Current link rate
    - asus_router_ports_max_rate_mbps: Maximum supported rate
    - asus_router_ports_slow_speed: Operating at reduced speed (0/1)
    - asus_router_ports_group: Port group (one-hot)
    - asus_router_ports_port: Port info (Info metric)
    """

    name = "ports"

    def _create_metrics(self) -> None:
        """Create port metrics."""
        self._plugged = Gauge(
            "asus_router_ports_plugged",
            "Port connection status (0/1)",
            ["product_id", "port_id"],
            registry=self._registry,
        )
        self._register_metric(self._plugged)

        self._link_rate = Gauge(
            "asus_router_ports_link_rate_mbps",
            "Port current link rate in Mbps",
            ["product_id", "port_id"],
            registry=self._registry,
        )
        self._register_metric(self._link_rate)

        self._max_rate = Gauge(
            "asus_router_ports_max_rate_mbps",
            "Port maximum supported rate in Mbps",
            ["product_id", "port_id"],
            registry=self._registry,
        )
        self._register_metric(self._max_rate)

        self._slow_speed = Gauge(
            "asus_router_ports_slow_speed",
            "Port operating at reduced speed (0/1)",
            ["product_id", "port_id"],
            registry=self._registry,
        )
        self._register_metric(self._slow_speed)

        self._port_group = Gauge(
            "asus_router_ports_group",
            "Port group (one-hot)",
            ["product_id", "port_id", "port_group"],
            registry=self._registry,
        )
        self._register_metric(self._port_group)

        self._port_info = Info(
            "asus_router_ports_port",
            "Port detailed information",
            ["product_id", "port_id"],
            registry=self._registry,
        )
        self._register_metric(self._port_info)

    def _collect_metrics(
        self,
        router_client: RouterClientProtocol,
        router_info: Any
    ) -> None:
        """Collect port metrics from router."""
        product_id = getattr(router_info, 'product_id', 'unknown')

        ports_info = getattr(router_info, 'ports_info', None)
        if not ports_info:
            logger.debug("[%s] No port info available", product_id)
            return

        for port_info in ports_info:
            self._collect_port_metrics(product_id, port_info)

        logger.debug("[%s] Port metrics collected: %d ports", product_id, len(ports_info))

    def _collect_port_metrics(self, product_id: str, port_info: Any) -> None:
        """Collect metrics for a single port."""
        port_id = getattr(port_info, 'id', 'unknown')

        # Plugged status
        plugged = getattr(port_info, 'plugged', False)
        self._plugged.labels(product_id=product_id, port_id=port_id).set(1 if plugged else 0)

        # Link rate
        link_rate = getattr(port_info, 'current_speed_rate_mbps', 0)
        self._link_rate.labels(product_id=product_id, port_id=port_id).set(link_rate)

        # Max rate
        max_rate = getattr(port_info, 'max_supported_speed_rate_mbps', 0)
        self._max_rate.labels(product_id=product_id, port_id=port_id).set(max_rate)

        # Slow speed
        slow_speed = getattr(port_info, 'is_slow_speed', False)
        self._slow_speed.labels(product_id=product_id, port_id=port_id).set(1 if slow_speed else 0)

        # Port group (one-hot)
        port_group = getattr(port_info, 'group', None)
        if port_group:
            self._set_onehot_port_group(product_id, port_id, port_group)

        # Port info
        self._port_info.labels(product_id=product_id, port_id=port_id).info({
            "special_port_name": getattr(port_info, 'special_port_name', ''),
        })

    def _set_onehot_port_group(self, product_id: str, port_id: str, current_group: Any) -> None:
        """Set one-hot encoding for port group."""
        for group in PortGroup:
            value = 1 if group == current_group else 0
            self._port_group.labels(
                product_id=product_id,
                port_id=port_id,
                port_group=group.name
            ).set(value)
