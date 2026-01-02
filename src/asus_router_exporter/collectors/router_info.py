"""
Router info metrics collector.

Collects:
- Router static information
- Uptime
- Software mode
- Reboot schedule
- Software update availability
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import Gauge, Info

from ..client.models import SwMode
from ..core.protocols import RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class RouterInfoCollector(BaseCollector):
    """
    Collector for router information metrics.

    Metrics:
    - asus_router_info: Router information (Info metric)
    - asus_router_uptime_seconds: Router uptime in seconds
    - asus_router_sw_mode: Router software mode (one-hot)
    - asus_router_reboot_schedule_second_until_next: Seconds until next reboot
    - asus_router_software_update_available: Software update available (0/1)
    """

    name = "router_info"

    def _create_metrics(self) -> None:
        """Create router info metrics."""
        # Info metric without product_id label is intentional. This exporter runs
        # one instance per router (single-router architecture), so product_id is
        # embedded in the info dict itself. Adding it as a label would be redundant
        # and change the metric name structure unnecessarily.
        self._info = Info(
            "asus_router",
            "Router information (static details such as product ID, model, firmware)",
            registry=self._registry,
        )
        self._register_metric(self._info)

        self._uptime = Gauge(
            "asus_router_uptime_seconds",
            "Router uptime in seconds",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._uptime)

        self._sw_mode = Gauge(
            "asus_router_sw_mode",
            "Asus router mode (one-hot)",
            ["product_id", "sw_mode"],
            registry=self._registry,
        )
        self._register_metric(self._sw_mode)

        self._next_reboot = Gauge(
            "asus_router_reboot_schedule_second_until_next",
            "Seconds until next scheduled reboot",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._next_reboot)

        self._update_available = Gauge(
            "asus_router_software_update_available",
            "Software update available (0/1)",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._update_available)

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect router info metrics."""
        product_id = getattr(router_info, "product_id", "unknown")

        # Static info
        self._info.info(
            {
                "product_id": product_id,
                "firmware": f"{getattr(router_info, 'firmver', '')}_{getattr(router_info, 'extendno', '')}",
                "serial": getattr(router_info, "serial_no", ""),
                "hostname": getattr(router_info, "lan_hostname", ""),
                "mac": getattr(router_info, "lan_hwaddr", ""),
            }
        )

        # Uptime (with validation)
        uptime = getattr(router_info, "uptime", None)
        if uptime and hasattr(uptime, "boottime"):
            boottime = uptime.boottime
            # Validate boottime is a reasonable positive value
            if isinstance(boottime, (int, float)) and boottime > 0:
                self._uptime.labels(product_id=product_id).set(boottime)
            else:
                logger.debug("[%s] Invalid boottime value: %s", product_id, boottime)
                self._uptime.labels(product_id=product_id).set(float("nan"))
        else:
            self._uptime.labels(product_id=product_id).set(float("nan"))

        # Software mode (one-hot encoding)
        sw_mode = getattr(router_info, "sw_mode", None)
        if sw_mode:
            self._set_onehot_sw_mode(product_id, sw_mode)

        # Reboot schedule
        reboot_schedule = getattr(router_info, "reboot_schedule", None)
        if reboot_schedule and getattr(reboot_schedule, "until_ms", None) is not None:
            self._next_reboot.labels(product_id=product_id).set(reboot_schedule.until_ms / 1000)
        else:
            self._next_reboot.labels(product_id=product_id).set(float("nan"))

        # Software update
        update_available = getattr(router_info, "software_update_available", False)
        self._update_available.labels(product_id=product_id).set(1 if update_available else 0)

        logger.debug("[%s] Router info collected", product_id)

    def _set_onehot_sw_mode(self, product_id: str, current_mode: Any) -> None:
        """Set one-hot encoding for software mode."""
        for mode in SwMode:
            value = 1 if mode == current_mode else 0
            self._sw_mode.labels(product_id=product_id, sw_mode=mode.name).set(value)
