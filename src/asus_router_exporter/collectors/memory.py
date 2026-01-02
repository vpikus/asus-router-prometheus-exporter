"""
Memory metrics collector.

Collects:
- Total memory
- Used memory
- Free memory
- Memory usage percentage
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import Gauge

from ..core.protocols import RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class MemoryCollector(BaseCollector):
    """
    Collector for memory metrics.

    Metrics:
    - asus_router_memory_total_bytes: Total memory in bytes
    - asus_router_memory_used_bytes: Used memory in bytes
    - asus_router_memory_free_bytes: Free memory in bytes
    - asus_router_memory_used_percent: Memory usage percentage
    """

    name = "memory"

    def _create_metrics(self) -> None:
        """Create memory metrics."""
        self._total_bytes = Gauge(
            "asus_router_memory_total_bytes",
            "Total memory in bytes",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._total_bytes)

        self._used_bytes = Gauge(
            "asus_router_memory_used_bytes",
            "Used memory in bytes",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._used_bytes)

        self._free_bytes = Gauge(
            "asus_router_memory_free_bytes",
            "Free memory in bytes",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._free_bytes)

        self._used_percent = Gauge(
            "asus_router_memory_used_percent",
            "Memory usage percentage (used / total * 100)",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._used_percent)

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect memory metrics from router."""
        product_id = getattr(router_info, "product_id", "unknown")

        try:
            mem = router_client.get_memory_usage()
        except Exception:
            logger.warning("[%s] Memory collection failed", product_id, exc_info=True)
            self._set_gauge_nan(product_id)
            return

        # Convert KB to bytes
        total_bytes = self._kb_to_bytes(getattr(mem, "total_kb", None))
        used_bytes = self._kb_to_bytes(getattr(mem, "used_kb", None))
        free_bytes = self._kb_to_bytes(getattr(mem, "free_kb", None))

        self._set_gauge_safe(self._total_bytes.labels(product_id=product_id), total_bytes)
        self._set_gauge_safe(self._used_bytes.labels(product_id=product_id), used_bytes)
        self._set_gauge_safe(self._free_bytes.labels(product_id=product_id), free_bytes)

        # Calculate percentage
        if total_bytes and total_bytes > 0 and used_bytes is not None:
            percent = max(0.0, min(100.0, (used_bytes / total_bytes) * 100.0))
            self._used_percent.labels(product_id=product_id).set(percent)
        else:
            self._used_percent.labels(product_id=product_id).set(float("nan"))

        logger.debug(
            "[%s] Memory: total=%s, used=%s, free=%s",
            product_id,
            getattr(mem, "total_kb", "N/A"),
            getattr(mem, "used_kb", "N/A"),
            getattr(mem, "free_kb", "N/A"),
        )

    def _set_gauge_nan(self, product_id: str) -> None:
        """Set all gauges to NaN for error cases."""
        self._total_bytes.labels(product_id=product_id).set(float("nan"))
        self._used_bytes.labels(product_id=product_id).set(float("nan"))
        self._free_bytes.labels(product_id=product_id).set(float("nan"))
        self._used_percent.labels(product_id=product_id).set(float("nan"))

    @staticmethod
    def _kb_to_bytes(kb: int | float | None) -> float | None:
        """Convert kilobytes to bytes."""
        if kb is None:
            return None
        return float(kb) * 1024

    @staticmethod
    def _set_gauge_safe(gauge_child: Any, value: float | None) -> None:
        """Set gauge value safely, using NaN for None values."""
        if value is None:
            gauge_child.set(float("nan"))
        else:
            gauge_child.set(value)
