"""
Base collector class for metric collectors.

Provides common functionality for all collectors including:
- Prometheus registry management
- Configuration access
- Metric lifecycle (create, update, clear)
- Error handling
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from prometheus_client import CollectorRegistry

from ..core.exceptions import CollectorError
from ..core.protocols import ConfigProviderProtocol, RouterClientProtocol

if TYPE_CHECKING:
    from prometheus_client.metrics import MetricWrapperBase

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """
    Abstract base class for metric collectors.

    Subclasses must implement:
    - name: Unique collector name
    - _create_metrics(): Initialize Prometheus metrics
    - _collect_metrics(): Collect and update metrics

    Example:
        class CPUCollector(BaseCollector):
            name = "cpu"

            def _create_metrics(self):
                self._usage = Gauge(
                    "asus_router_cpu_usage_percent",
                    "CPU usage percentage",
                    ["product_id"],
                    registry=self._registry,
                )
                self._register_metric(self._usage)

            def _collect_metrics(self, router_client, router_info):
                product_id = getattr(router_info, 'product_id', 'unknown')
                usage = router_client.get_cpu_usage()
                self._usage.labels(product_id=product_id).set(usage)
    """

    # Subclasses must define this
    name: str = ""

    def __init__(
        self,
        registry: CollectorRegistry,
        config: ConfigProviderProtocol,
    ):
        """
        Initialize collector.

        Args:
            registry: Prometheus collector registry
            config: Configuration provider
        """
        self._registry = registry
        self._config = config
        self._metrics: list[MetricWrapperBase] = []
        self._collector_config = config.get_collector_config(self.name)
        self._enabled: bool = bool(self._collector_config.get("enabled", True))

        if self._enabled:
            self._create_metrics()
            logger.debug("Collector '%s' initialized", self.name)
        else:
            logger.info("Collector '%s' is disabled", self.name)

    @property
    def enabled(self) -> bool:
        """Check if collector is enabled."""
        return self._enabled

    def collect(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """
        Collect metrics from router.

        Args:
            router_client: Client for router API calls
            router_info: Router information (product_id, etc.)

        Raises:
            CollectorError: If collection fails
        """
        if not self._enabled:
            return

        try:
            self._collect_metrics(router_client, router_info)
            logger.debug("Collector '%s' completed successfully", self.name)
        except Exception as e:
            logger.exception("Collector '%s' failed", self.name)
            raise CollectorError(self.name, str(e)) from e

    def cleanup(self) -> None:
        """Clean up collector resources and clear metrics."""
        self._clear_metrics()
        logger.debug("Collector '%s' cleaned up", self.name)

    @abstractmethod
    def _create_metrics(self) -> None:
        """
        Create Prometheus metrics.

        Subclasses must implement this to define their metrics.
        Metrics should be stored as instance attributes and added
        to self._metrics list for cleanup.
        """
        pass

    @abstractmethod
    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """
        Collect and update metrics.

        Subclasses must implement this to fetch data from router
        and update their metrics.

        Args:
            router_client: Client for router API calls
            router_info: Router information
        """
        pass

    def _clear_metrics(self) -> None:
        """Clear all registered metrics."""
        for metric in self._metrics:
            self._clear_metric(metric)

    def _clear_metric(self, metric: MetricWrapperBase) -> None:
        """
        Clear a single metric using the official thread-safe API.

        Uses prometheus_client's clear() method which properly handles
        locking and works with all metric types (Gauge, Counter, Info, etc.).
        """
        try:
            # Use the official clear() API which is thread-safe
            if hasattr(metric, "clear"):
                metric.clear()
        except Exception:
            logger.warning("Failed to clear metric in collector '%s'", self.name, exc_info=True)

    def _register_metric(self, metric: MetricWrapperBase) -> MetricWrapperBase:
        """
        Register a metric for cleanup tracking.

        Args:
            metric: The Prometheus metric to register

        Returns:
            The same metric (for chaining)
        """
        self._metrics.append(metric)
        return metric

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get collector-specific configuration value.

        Args:
            key: Configuration key within collector config
            default: Default value if not found

        Returns:
            Configuration value
        """
        return self._collector_config.get(key, default)


class LabeledMetricsMixin:
    """
    Mixin for collectors that use labeled metrics.

    Provides helper methods for managing metrics with labels,
    including tracking active label combinations for cleanup.
    """

    def __init__(self) -> None:
        self._active_labels: dict[str, set[tuple[Any, ...]]] = {}

    def _track_labels(self, metric_name: str, labels: tuple) -> None:
        """
        Track active label combination for a metric.

        Args:
            metric_name: Name of the metric
            labels: Tuple of label values
        """
        if metric_name not in self._active_labels:
            self._active_labels[metric_name] = set()
        self._active_labels[metric_name].add(labels)

    def _get_stale_labels(self, metric_name: str, current_labels: set) -> set:
        """
        Find label combinations that are no longer active.

        Args:
            metric_name: Name of the metric
            current_labels: Set of currently active label tuples

        Returns:
            Set of stale label tuples to be removed
        """
        previous = self._active_labels.get(metric_name, set())
        return previous - current_labels

    def _update_active_labels(self, metric_name: str, current_labels: set) -> None:
        """
        Update the active labels for a metric.

        Args:
            metric_name: Name of the metric
            current_labels: Set of currently active label tuples
        """
        self._active_labels[metric_name] = current_labels

    def _remove_stale_metrics(self, metric: Any, metric_name: str, current_labels: set) -> None:
        """
        Remove metrics for stale label combinations.

        Args:
            metric: The Prometheus metric object
            metric_name: Name of the metric
            current_labels: Set of currently active label tuples
        """
        stale = self._get_stale_labels(metric_name, current_labels)
        for labels in stale:
            try:
                metric.remove(*labels)
            except Exception as e:
                logger.debug("Could not remove stale labels %s from %s: %s", labels, metric_name, str(e))
        self._update_active_labels(metric_name, current_labels)
