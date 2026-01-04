"""
CPU metrics collector.

Collects:
- CPU temperature
- CPU usage (counter)
- CPU total time (counter)
- CPU usage percentage (gauge)
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge

from ..core.protocols import ConfigProviderProtocol, RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class CPUCollector(BaseCollector):
    """
    Collector for CPU metrics.

    Metrics:
    - asus_router_cpu_temperature_celsius: CPU temperature
    - asus_router_cpu_usage: CPU usage counter (cumulative)
    - asus_router_cpu_total: CPU total time counter (cumulative)
    - asus_router_cpu_usage_percent: CPU usage percentage (calculated from deltas)

    Configuration:
    - enabled: Whether to collect CPU metrics (default: True)
    - track_per_core: Whether to track per-core metrics (default: True)
    """

    name = "cpu"

    def __init__(
        self,
        registry: CollectorRegistry,
        config: ConfigProviderProtocol,
    ):
        # Track previous samples for percentage calculation.
        # Design Note: This dict is inherently bounded because:
        # 1. Keys are "{product_id}:{cpu_id}" - typically 1-4 CPUs per router
        # 2. Single-router architecture means one product_id
        # 3. Routers have fixed CPU counts that don't change at runtime
        # 4. cleanup() properly clears this on shutdown
        # Therefore unbounded growth is not a concern here.
        self._previous_samples: dict[str, dict[str, int]] = {}
        super().__init__(registry, config)

    def _create_metrics(self) -> None:
        """Create CPU metrics."""
        self._temperature: Gauge = Gauge(
            "asus_router_cpu_temperature_celsius",
            "CPU temperature in Celsius",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._temperature)

        self._usage_counter: Counter = Counter(
            "asus_router_cpu_usage",
            "CPU usage time (cumulative)",
            ["product_id", "cpu_id"],
            registry=self._registry,
        )
        self._register_metric(self._usage_counter)

        self._total_counter: Counter = Counter(
            "asus_router_cpu_total",
            "CPU total time (cumulative)",
            ["product_id", "cpu_id"],
            registry=self._registry,
        )
        self._register_metric(self._total_counter)

        self._usage_percent: Gauge = Gauge(
            "asus_router_cpu_usage_percent",
            "CPU usage percentage (calculated from usage/total deltas)",
            ["product_id", "cpu_id"],
            registry=self._registry,
        )
        self._register_metric(self._usage_percent)

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect CPU metrics from router."""
        product_id = getattr(router_info, "product_id", "unknown")

        # Collect temperature
        self._collect_temperature(router_client, product_id)

        # Collect usage metrics
        self._collect_usage(router_client, product_id)

    def _collect_temperature(self, router_client: RouterClientProtocol, product_id: str) -> None:
        """Collect CPU temperature."""
        try:
            temp_info = router_client.get_core_temp()
            if temp_info and hasattr(temp_info, "cpu"):
                self._temperature.labels(product_id=product_id).set(temp_info.cpu)
                logger.debug("[%s] CPU temperature: %.1f°C", product_id, temp_info.cpu)
        except Exception:
            logger.warning("[%s] CPU temperature collection failed", product_id, exc_info=True)

    def _collect_usage(self, router_client: RouterClientProtocol, product_id: str) -> None:
        """Collect CPU usage metrics."""
        try:
            cpu_infos = router_client.get_cpu_usage()
        except Exception:
            logger.warning("[%s] CPU usage collection failed", product_id, exc_info=True)
            return

        for i, cpu_info in enumerate(cpu_infos):
            cpu_id = str(i)
            self._process_cpu_sample(product_id, cpu_id, cpu_info)

        logger.debug("[%s] CPU metrics collected: %d CPUs", product_id, len(cpu_infos))

    def _process_cpu_sample(self, product_id: str, cpu_id: str, cpu_info: Any) -> None:
        """Process a single CPU sample and update metrics."""
        usage = getattr(cpu_info, "usage", 0)
        total = getattr(cpu_info, "total", 0)

        # Use composite key to support multiple routers
        sample_key = f"{product_id}:{cpu_id}"
        prev = self._previous_samples.get(sample_key)

        if prev is not None:
            # Calculate deltas
            delta_usage = self._calculate_delta(usage, prev["usage"])
            delta_total = self._calculate_delta(total, prev["total"])

            # Update counters with deltas
            self._usage_counter.labels(product_id=product_id, cpu_id=cpu_id).inc(max(0, delta_usage))

            self._total_counter.labels(product_id=product_id, cpu_id=cpu_id).inc(max(0, delta_total))

            # Calculate and set percentage (clamped to [0, 100])
            if delta_total > 0:
                percent = max(0.0, min(100.0, (delta_usage / delta_total) * 100.0))
                self._usage_percent.labels(product_id=product_id, cpu_id=cpu_id).set(percent)
                logger.debug(
                    "[%s] CPU %s: usage Δ=%d, total Δ=%d, %.1f%%", product_id, cpu_id, delta_usage, delta_total, percent
                )
            else:
                # No time elapsed, set to NaN
                self._usage_percent.labels(product_id=product_id, cpu_id=cpu_id).set(float("nan"))
        else:
            # First sample, set percentage to NaN
            self._usage_percent.labels(product_id=product_id, cpu_id=cpu_id).set(float("nan"))

        # Store current sample for next iteration
        self._previous_samples[sample_key] = {"usage": usage, "total": total}

    @staticmethod
    def _calculate_delta(current: int, previous: int) -> int:
        """
        Calculate delta between current and previous values.

        Handles counter wrapping by returning 0 to skip that sample.
        This is acceptable as wraps are rare and Prometheus rate()
        function handles this automatically in queries.

        Args:
            current: Current counter value
            previous: Previous counter value

        Returns:
            Delta value (always positive or zero)
        """
        if current >= previous:
            return current - previous
        # Counter wrapped or was reset, skip this sample
        logger.debug("Counter wrap detected: current=%d < previous=%d, skipping", current, previous)
        return 0

    def reset_state(self) -> None:
        """Reset internal state on node switch.

        Clears previous samples to prevent incorrect delta calculations
        when switching between AiMesh nodes with different CPU counters.
        """
        self._previous_samples.clear()
        logger.debug("[%s] CPU collector state reset", self.name)

    def cleanup(self) -> None:
        """Clean up collector and reset state."""
        super().cleanup()
        self._previous_samples.clear()
