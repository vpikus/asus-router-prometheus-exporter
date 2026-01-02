"""
WAN metrics collector.

Collects:
- Dual WAN status and mode
- Link internet status
- WAN connection state, substate, auxstate
- WAN online status
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import Gauge

from ..client import models as client_models
from ..client.models import WanMode
from ..core.protocols import RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class WANCollector(BaseCollector):
    """
    Collector for WAN metrics.

    Metrics:
    - asus_router_dualwan_enabled
    - asus_router_dualwan_mode
    - asus_router_link_internet_status
    - asus_router_wan_connection_state
    - asus_router_wan_connection_substate
    - asus_router_wan_connection_auxstate
    - asus_router_wan_connection_online
    - asus_router_wan_status
    - asus_router_wan_active
    """

    name = "wan"

    def _create_metrics(self) -> None:
        """Create WAN metrics."""
        self._dualwan_enabled = Gauge(
            "asus_router_dualwan_enabled",
            "Dual WAN enabled",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._dualwan_enabled)

        self._dualwan_mode = Gauge(
            "asus_router_dualwan_mode",
            "Dual WAN mode (one-hot)",
            ["product_id", "mode"],
            registry=self._registry,
        )
        self._register_metric(self._dualwan_mode)

        self._link_internet = Gauge(
            "asus_router_link_internet_status",
            "Link internet status (0/1)",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._link_internet)

        self._wan_state = Gauge(
            "asus_router_wan_connection_state",
            "WAN state (one-hot)",
            ["product_id", "unit", "state"],
            registry=self._registry,
        )
        self._register_metric(self._wan_state)

        self._wan_substate = Gauge(
            "asus_router_wan_connection_substate",
            "WAN substate (one-hot)",
            ["product_id", "unit", "substate"],
            registry=self._registry,
        )
        self._register_metric(self._wan_substate)

        self._wan_auxstate = Gauge(
            "asus_router_wan_connection_auxstate",
            "WAN cable/aux state (one-hot)",
            ["product_id", "unit", "auxstate"],
            registry=self._registry,
        )
        self._register_metric(self._wan_auxstate)

        self._wan_online = Gauge(
            "asus_router_wan_connection_online",
            "WAN online status (0/1)",
            ["product_id", "unit"],
            registry=self._registry,
        )
        self._register_metric(self._wan_online)

        self._wan_status = Gauge(
            "asus_router_wan_status",
            "WAN status (one-hot)",
            ["product_id", "unit", "status"],
            registry=self._registry,
        )
        self._register_metric(self._wan_status)

        self._wan_active = Gauge(
            "asus_router_wan_active",
            "WAN active (0/1)",
            ["product_id", "unit"],
            registry=self._registry,
        )
        self._register_metric(self._wan_active)

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect WAN metrics from router."""
        product_id = getattr(router_info, "product_id", "unknown")

        try:
            wan_info = router_client.get_network_wan_info()
        except Exception:
            logger.warning("[%s] WAN collection failed", product_id, exc_info=True)
            return

        # Dual WAN settings (accessed through dual_wan_info)
        dual_wan_info = getattr(wan_info, "dual_wan_info", None)
        dualwan_enabled = getattr(dual_wan_info, "enabled", False) if dual_wan_info else False
        self._dualwan_enabled.labels(product_id=product_id).set(1 if dualwan_enabled else 0)

        # Dual WAN mode (one-hot) - accessed through dual_wan_info.wans_mode
        if dual_wan_info:
            dualwan_mode = getattr(dual_wan_info, "wans_mode", None)
            if dualwan_mode:
                self._set_onehot_dualwan_mode(product_id, dualwan_mode)
            else:
                self._zero_onehot_dualwan_mode(product_id)
        else:
            self._zero_onehot_dualwan_mode(product_id)

        # Link internet status
        link_internet = getattr(wan_info, "link_internet", None)
        if link_internet is not None:
            # link_internet could be an enum or bool
            if hasattr(link_internet, "value"):
                self._link_internet.labels(product_id=product_id).set(1 if link_internet.value else 0)
            else:
                self._link_internet.labels(product_id=product_id).set(1 if link_internet else 0)

        # WAN units (primary and secondary)
        primary_wan = getattr(wan_info, "primary_wan", None)
        secondary_wan = getattr(wan_info, "secondary_wan", None)

        if primary_wan:
            self._collect_wan_unit_metrics(product_id, "0", primary_wan)
        else:
            self._zero_wan_unit_metrics(product_id, "0")

        if secondary_wan:
            self._collect_wan_unit_metrics(product_id, "1", secondary_wan)
        else:
            self._zero_wan_unit_metrics(product_id, "1")

        logger.debug("[%s] WAN metrics collected", product_id)

    def _collect_wan_unit_metrics(self, product_id: str, unit: str, wan_unit: Any) -> None:
        """Collect metrics for a single WAN unit."""
        # Get connection_info which contains state, substate, auxstate
        connection_info = getattr(wan_unit, "connection_info", None)

        if connection_info:
            # State (one-hot)
            state = getattr(connection_info, "state", None)
            if state is not None:
                self._set_onehot_enum(self._wan_state, product_id, unit, state, "state", "WanState")

            # Substate (one-hot)
            substate = getattr(connection_info, "substate", None)
            if substate is not None:
                self._set_onehot_enum(self._wan_substate, product_id, unit, substate, "substate", "WanSubState")

            # Auxstate (one-hot)
            auxstate = getattr(connection_info, "auxstate", None)
            if auxstate is not None:
                self._set_onehot_enum(self._wan_auxstate, product_id, unit, auxstate, "auxstate", "WanAuxState")

            # Online status (derived from connection_info.is_connected)
            online = getattr(connection_info, "is_connected", False)
            self._wan_online.labels(product_id=product_id, unit=unit).set(1 if online else 0)
        else:
            # No connection_info available, set online to 0
            self._wan_online.labels(product_id=product_id, unit=unit).set(0)

        # WAN status (one-hot) - status is directly on WanInfo, type is WanStatus
        status = getattr(wan_unit, "status", None)
        if status is not None:
            self._set_onehot_enum(self._wan_status, product_id, unit, status, "status", "WanStatus")

        # Active
        active = getattr(wan_unit, "active", False)
        self._wan_active.labels(product_id=product_id, unit=unit).set(1 if active else 0)

    def _set_onehot_dualwan_mode(self, product_id: str, current_mode: Any) -> None:
        """Set one-hot encoding for dual WAN mode."""
        for mode in WanMode:
            value = 1 if mode == current_mode else 0
            self._dualwan_mode.labels(product_id=product_id, mode=mode.name).set(value)

    def _zero_onehot_dualwan_mode(self, product_id: str) -> None:
        """Zero out all dual WAN mode values."""
        for mode in WanMode:
            self._dualwan_mode.labels(product_id=product_id, mode=mode.name).set(0)

    def _zero_wan_unit_metrics(self, product_id: str, unit: str) -> None:
        """Zero out all metrics for a WAN unit that doesn't exist."""
        # Zero out state one-hot
        self._zero_onehot_enum(self._wan_state, product_id, unit, "state", "WanState")
        # Zero out substate one-hot
        self._zero_onehot_enum(self._wan_substate, product_id, unit, "substate", "WanSubState")
        # Zero out auxstate one-hot
        self._zero_onehot_enum(self._wan_auxstate, product_id, unit, "auxstate", "WanAuxState")
        # Zero out status one-hot
        self._zero_onehot_enum(self._wan_status, product_id, unit, "status", "WanStatus")
        # Zero out online and active
        self._wan_online.labels(product_id=product_id, unit=unit).set(0)
        self._wan_active.labels(product_id=product_id, unit=unit).set(0)

    def _zero_onehot_enum(self, gauge: Gauge, product_id: str, unit: str, label_name: str, enum_name: str) -> None:
        """Zero out all values for a one-hot enum."""
        enum_class = getattr(client_models, enum_name, None)
        if enum_class:
            for enum_val in enum_class:
                gauge.labels(product_id=product_id, unit=unit, **{label_name: enum_val.name}).set(0)

    def _set_onehot_enum(
        self, gauge: Gauge, product_id: str, unit: str, current_value: Any, label_name: str, enum_name: str
    ) -> None:
        """Set one-hot encoding for an enum value."""
        enum_class = getattr(client_models, enum_name, None)
        if enum_class:
            for enum_val in enum_class:
                value = 1 if enum_val == current_value else 0
                gauge.labels(product_id=product_id, unit=unit, **{label_name: enum_val.name}).set(value)
        else:
            gauge.labels(product_id=product_id, unit=unit, **{label_name: str(current_value)}).set(1)
