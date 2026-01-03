"""
Circuit breaker for fault tolerance.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from ...metrics.self_metrics import CircuitBreakerStateValue, SelfMetrics
from ..exceptions import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    enabled: bool = True
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3


@dataclass
class CircuitBreakerState:
    """Internal state for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_calls: int = 0
    lock: Lock = field(default_factory=Lock)


class CircuitBreaker:
    """
    Circuit breaker for fault tolerance.

    Prevents cascading failures by failing fast when a service is unhealthy.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service is failing, requests are blocked
    - HALF_OPEN: Testing if service has recovered

    Note:
        This implementation releases the lock during function execution to avoid
        holding it during potentially long operations. While this creates a
        theoretical TOCTOU (time-of-check-time-of-use) race condition, it is
        benign in this application because the metrics collection loop is
        single-threaded. If used in a multi-threaded context, consider adding
        additional synchronization or accepting the minor race window.

    Example:
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))
        try:
            result = breaker.execute(risky_function)
        except CircuitBreakerOpenError:
            # Circuit is open, handle gracefully
            pass
    """

    def __init__(
        self, config: CircuitBreakerConfig | None = None, *, metrics: SelfMetrics | None = None
    ):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
            metrics: Optional SelfMetrics instance for recording metrics.
                    If None, lazily fetches from SelfMetrics.get_instance() on first use.
        """
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState()
        self._metrics = metrics
        self._metrics_initialized = False

    def _get_metrics(self) -> SelfMetrics:
        """
        Get metrics instance, lazily initializing if needed.

        On first call, also sets initial circuit breaker state in metrics.

        Note:
            This method reads/writes _metrics_initialized without lock protection.
            A theoretical race exists if two threads call this before initialization,
            but it's benign: initialization is idempotent (sets state=CLOSED,
            failure_count=0, recovery_time=0), so redundant initialization causes
            no harm. Adding lock acquisition here would add overhead with no benefit.
        """
        if self._metrics is None:
            self._metrics = SelfMetrics.get_instance()
        if not self._metrics_initialized:
            self._metrics.set_circuit_breaker_state(CircuitBreakerStateValue.CLOSED)
            self._metrics.set_circuit_breaker_failure_count(0)
            self._metrics.set_circuit_breaker_recovery_time(0)
            self._metrics_initialized = True
        return self._metrics

    @property
    def state(self) -> CircuitState:
        """
        Get current circuit state.

        Note:
            This property reads without lock protection for observability purposes.
            In multi-threaded contexts, the returned value may be slightly stale
            if another thread is mid-transition. This is acceptable for monitoring
            and consistent with the single-threaded usage documented in the class.
        """
        return self._state.state

    @property
    def failure_count(self) -> int:
        """
        Get current failure count.

        Note:
            This property reads without lock protection for observability purposes.
            In multi-threaded contexts, the returned value may be slightly stale.
            This is acceptable for monitoring and consistent with the single-threaded
            usage documented in the class.
        """
        return self._state.failure_count

    def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute function through circuit breaker.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        if not self.config.enabled:
            return func(*args, **kwargs)

        # Note: Lock is released before function execution to avoid holding it during
        # potentially long-running operations. This creates a TOCTOU window where multiple
        # threads could pass the half-open check simultaneously, potentially exceeding
        # half_open_max_calls. This is acceptable behavior for circuit breakers - the limit
        # is a guideline, not a hard guarantee, and the alternative (holding lock during
        # execution) would serialize all protected calls which defeats the purpose.
        with self._state.lock:
            time_until_recovery = self._check_state_transition()

            if self._state.state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(f"Circuit breaker is open. Recovery in {time_until_recovery:.1f}s")

            if self._state.state == CircuitState.HALF_OPEN:
                if self._state.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError("Circuit breaker is half-open but max test calls reached")
                self._state.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def _check_state_transition(self) -> float:
        """
        Check and perform state transitions based on current conditions.

        Returns:
            Time until recovery in seconds (0 if not in OPEN state or transitioned)

        Note:
            This method calls `_get_metrics()` while the caller holds `self._state.lock`.
            If `SelfMetrics.get_instance()` acquires `_singleton_lock`, there's a theoretical
            lock ordering concern. However, SelfMetrics never calls back into CircuitBreaker,
            so no circular dependency exists. The single-threaded usage (documented in class
            docstring) further mitigates any concern.
        """
        if self._state.state == CircuitState.OPEN:
            time_until_recovery = self._time_until_recovery()
            metrics = self._get_metrics()
            if time_until_recovery <= 0:
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                self._state.state = CircuitState.HALF_OPEN
                self._state.half_open_calls = 0
                # Record state transition metrics
                metrics.record_circuit_breaker_transition("open", "half_open")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.HALF_OPEN)
                metrics.set_circuit_breaker_recovery_time(0)
                return 0
            else:
                # Update recovery time countdown so it's visible in metrics
                metrics.set_circuit_breaker_recovery_time(time_until_recovery)
                return time_until_recovery
        return 0

    def _time_until_recovery(self) -> float:
        """Calculate time until recovery attempt."""
        elapsed = time.time() - self._state.last_failure_time
        return max(0, self.config.recovery_timeout - elapsed)

    def _record_success(self) -> None:
        """Record a successful execution."""
        with self._state.lock:
            # Check inside lock to avoid data race between state and failure_count reads
            if self._state.state == CircuitState.CLOSED and self._state.failure_count == 0:
                return

            metrics = self._get_metrics()
            if self._state.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker transitioning to CLOSED after successful test")
                self._state.state = CircuitState.CLOSED
                metrics.record_circuit_breaker_transition("half_open", "closed")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.CLOSED)
                metrics.set_circuit_breaker_recovery_time(0)
            self._state.failure_count = 0
            self._state.half_open_calls = 0
            metrics.set_circuit_breaker_failure_count(0)

    def _record_failure(self) -> None:
        """Record a failed execution."""
        with self._state.lock:
            previous_state = self._state.state
            self._state.failure_count += 1
            self._state.last_failure_time = time.time()

            metrics = self._get_metrics()
            metrics.set_circuit_breaker_failure_count(self._state.failure_count)

            if self._state.state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker transitioning to OPEN after failed test")
                self._state.state = CircuitState.OPEN
                metrics.record_circuit_breaker_transition("half_open", "open")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.OPEN)
                metrics.set_circuit_breaker_recovery_time(self.config.recovery_timeout)
            elif self._state.failure_count >= self.config.failure_threshold:
                logger.warning("Circuit breaker transitioning to OPEN after %d failures", self._state.failure_count)
                self._state.state = CircuitState.OPEN
                from_state = "closed" if previous_state == CircuitState.CLOSED else previous_state.value
                metrics.record_circuit_breaker_transition(from_state, "open")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.OPEN)
                metrics.set_circuit_breaker_recovery_time(self.config.recovery_timeout)

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._state.lock:
            self._state.state = CircuitState.CLOSED
            self._state.failure_count = 0
            self._state.last_failure_time = 0.0
            self._state.half_open_calls = 0
            # Update metrics to reflect reset state
            metrics = self._get_metrics()
            metrics.set_circuit_breaker_state(CircuitBreakerStateValue.CLOSED)
            metrics.set_circuit_breaker_failure_count(0)
            metrics.set_circuit_breaker_recovery_time(0)
            logger.info("Circuit breaker reset to CLOSED")
