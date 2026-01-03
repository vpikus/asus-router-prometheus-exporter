"""
Self-metrics for observability of the exporter itself.

Provides metrics about:
- Circuit breaker state and transitions
- Retry behavior
- Cache performance (hits/misses)
- Per-collector success/failure rates and duration
- Per-API call performance and counts
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import IntEnum
from threading import Lock

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

# Module-level lock for thread-safe singleton pattern
# (Created when module is imported, protected by Python's import machinery and GIL)
_singleton_lock = Lock()


class CircuitBreakerStateValue(IntEnum):
    """Numeric values for circuit breaker states in metrics."""

    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


# Default histogram buckets for API request durations (in seconds)
# Covers typical range from 10ms to 30s
DEFAULT_API_DURATION_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class SelfMetrics:
    """
    Singleton registry for exporter self-metrics.

    Thread-safe singleton that manages all internal observability metrics.
    Components access this via get_instance() to record their metrics.

    Usage:
        metrics = SelfMetrics.get_instance()
        metrics.record_retry_attempt()
        metrics.record_cache_hit("uptime")

        # For API timing:
        with metrics.track_api_call("get_cpu_usage"):
            result = client.get_cpu_usage()
    """

    _instance: SelfMetrics | None = None

    def __init__(self, registry: CollectorRegistry | None = None):
        """Initialize self-metrics. Use get_instance() instead."""
        self._registry = registry or REGISTRY
        self._create_metrics()

    @classmethod
    def get_instance(cls, registry: CollectorRegistry | None = None) -> SelfMetrics:
        """Get or create the singleton instance."""
        with _singleton_lock:
            if cls._instance is None:
                cls._instance = cls(registry)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset singleton (for testing only).

        WARNING: Not thread-safe during reset. Caller must ensure no other
        threads are accessing metrics during reset. Intended for test isolation only.
        """
        with _singleton_lock:
            if cls._instance is not None:
                cls._instance._unregister_metrics()
            cls._instance = None

    def _unregister_metrics(self) -> None:
        """Unregister all metrics from the registry."""
        metrics_to_unregister = [
            self._circuit_breaker_state,
            self._circuit_breaker_failure_count,
            self._circuit_breaker_transitions,
            self._circuit_breaker_recovery_time,
            self._retry_attempts,
            self._retries_exhausted,
            self._proactive_reauth,
            self._cache_hits,
            self._cache_misses,
            self._collector_success,
            self._collector_errors,
            self._collector_duration,
            self._api_requests,
            self._api_request_duration,
            self._api_errors,
        ]
        for metric in metrics_to_unregister:
            try:
                self._registry.unregister(metric)
            except Exception:
                pass  # Metric may not be registered

    def _create_metrics(self) -> None:
        """Create all self-metrics."""
        # Circuit breaker metrics
        self._circuit_breaker_state = Gauge(
            "asus_router_exporter_circuit_breaker_state",
            "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
            registry=self._registry,
        )
        self._circuit_breaker_failure_count = Gauge(
            "asus_router_exporter_circuit_breaker_failure_count",
            "Current failure count in circuit breaker",
            registry=self._registry,
        )
        self._circuit_breaker_transitions = Counter(
            "asus_router_exporter_circuit_breaker_state_transitions_total",
            "Total number of circuit breaker state transitions",
            ["from_state", "to_state"],
            registry=self._registry,
        )
        self._circuit_breaker_recovery_time = Gauge(
            "asus_router_exporter_circuit_breaker_recovery_seconds",
            "Seconds until circuit breaker attempts recovery (0 when closed)",
            registry=self._registry,
        )

        # Retry metrics
        self._retry_attempts = Counter(
            "asus_router_exporter_retry_attempts_total",
            "Total number of retry attempts (excludes initial attempt)",
            registry=self._registry,
        )
        self._retries_exhausted = Counter(
            "asus_router_exporter_retries_exhausted_total",
            "Total number of times all retries were exhausted",
            registry=self._registry,
        )

        # Authentication metrics
        self._proactive_reauth = Counter(
            "asus_router_exporter_proactive_reauth_total",
            "Total number of proactive re-authentications",
            registry=self._registry,
        )

        # Cache metrics
        self._cache_hits = Counter(
            "asus_router_exporter_cache_hits_total",
            "Total number of cache hits",
            ["cache_key"],
            registry=self._registry,
        )
        self._cache_misses = Counter(
            "asus_router_exporter_cache_misses_total",
            "Total number of cache misses",
            ["cache_key"],
            registry=self._registry,
        )

        # Collector metrics
        self._collector_success = Counter(
            "asus_router_exporter_collector_success_total",
            "Total number of successful collections per collector",
            ["collector"],
            registry=self._registry,
        )
        self._collector_errors = Counter(
            "asus_router_exporter_collector_errors_total",
            "Total number of collection errors per collector",
            ["collector"],
            registry=self._registry,
        )
        self._collector_duration = Gauge(
            "asus_router_exporter_collector_duration_seconds",
            "Duration of the last collection per collector",
            ["collector"],
            registry=self._registry,
        )

        # API performance metrics
        self._api_requests = Counter(
            "asus_router_exporter_api_requests_total",
            "Total number of API requests per method",
            ["method"],
            registry=self._registry,
        )
        self._api_request_duration = Histogram(
            "asus_router_exporter_api_request_duration_seconds",
            "Duration of API requests in seconds",
            ["method"],
            buckets=DEFAULT_API_DURATION_BUCKETS,
            registry=self._registry,
        )
        self._api_errors = Counter(
            "asus_router_exporter_api_errors_total",
            "Total number of API errors per method",
            ["method"],
            registry=self._registry,
        )

    # -------------------------------------------------------------------------
    # Circuit breaker recording methods
    # -------------------------------------------------------------------------

    def set_circuit_breaker_state(self, state: CircuitBreakerStateValue) -> None:
        """Set the current circuit breaker state."""
        self._circuit_breaker_state.set(state.value)

    def set_circuit_breaker_failure_count(self, count: int) -> None:
        """Set the current circuit breaker failure count."""
        self._circuit_breaker_failure_count.set(count)

    def record_circuit_breaker_transition(self, from_state: str, to_state: str) -> None:
        """Record a circuit breaker state transition."""
        self._circuit_breaker_transitions.labels(from_state=from_state, to_state=to_state).inc()

    def set_circuit_breaker_recovery_time(self, seconds: float) -> None:
        """Set the time until circuit breaker attempts recovery (0 when closed)."""
        self._circuit_breaker_recovery_time.set(max(0, seconds))

    # -------------------------------------------------------------------------
    # Retry recording methods
    # -------------------------------------------------------------------------

    def record_retry_attempt(self) -> None:
        """Record a retry attempt (not the initial attempt)."""
        self._retry_attempts.inc()

    def record_retries_exhausted(self) -> None:
        """Record that all retries were exhausted."""
        self._retries_exhausted.inc()

    # -------------------------------------------------------------------------
    # Authentication recording methods
    # -------------------------------------------------------------------------

    def record_proactive_reauth(self) -> None:
        """Record a proactive re-authentication event."""
        self._proactive_reauth.inc()

    # -------------------------------------------------------------------------
    # Cache recording methods
    # -------------------------------------------------------------------------

    def record_cache_hit(self, cache_key: str) -> None:
        """
        Record a cache hit.

        Args:
            cache_key: The cache key that was hit. Use only a bounded set of
                      keys (5-10) to avoid unbounded label cardinality.
        """
        self._cache_hits.labels(cache_key=cache_key).inc()

    def record_cache_miss(self, cache_key: str) -> None:
        """
        Record a cache miss.

        Args:
            cache_key: The cache key that was missed. Use only a bounded set of
                      keys (5-10) to avoid unbounded label cardinality.
        """
        self._cache_misses.labels(cache_key=cache_key).inc()

    # -------------------------------------------------------------------------
    # Collector recording methods
    # -------------------------------------------------------------------------

    def record_collector_success(self, collector_name: str) -> None:
        """Record a successful collection."""
        self._collector_success.labels(collector=collector_name).inc()

    def record_collector_error(self, collector_name: str) -> None:
        """Record a collection error."""
        self._collector_errors.labels(collector=collector_name).inc()

    def set_collector_duration(self, collector_name: str, duration: float) -> None:
        """Set the duration of the last collection for a collector."""
        self._collector_duration.labels(collector=collector_name).set(duration)

    # -------------------------------------------------------------------------
    # API performance recording methods
    # -------------------------------------------------------------------------

    def record_api_request(self, method: str, duration: float) -> None:
        """Record an API request with its duration."""
        self._api_requests.labels(method=method).inc()
        self._api_request_duration.labels(method=method).observe(duration)

    def record_api_error(self, method: str) -> None:
        """Record an API error."""
        self._api_errors.labels(method=method).inc()

    @contextmanager
    def track_api_call(self, method: str) -> Iterator[None]:
        """
        Context manager to track API call duration and errors.

        Usage:
            with metrics.track_api_call("get_cpu_usage"):
                result = client.get_cpu_usage()

        Records:
        - Request count and duration on success
        - Error count and duration on exception (re-raises the exception)

        Duration is always recorded to help distinguish quick failures
        (e.g., auth errors) from slow failures (e.g., timeouts).
        """
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            self.record_api_request(method, duration)
        except Exception:
            duration = time.time() - start_time
            self._api_request_duration.labels(method=method).observe(duration)
            self.record_api_error(method)
            raise
