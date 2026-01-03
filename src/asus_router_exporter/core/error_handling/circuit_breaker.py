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

    def __init__(self, config: CircuitBreakerConfig | None = None):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state.state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
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
            self._check_state_transition()

            if self._state.state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is open. Recovery in {self._time_until_recovery():.1f}s"
                )

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

    def _check_state_transition(self) -> None:
        """Check and perform state transitions based on current conditions."""
        if self._state.state == CircuitState.OPEN:
            if self._recovery_timeout_elapsed():
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                self._state.state = CircuitState.HALF_OPEN
                self._state.half_open_calls = 0
                # Record state transition metrics
                metrics = SelfMetrics.get_instance()
                metrics.record_circuit_breaker_transition("open", "half_open")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.HALF_OPEN)

    def _recovery_timeout_elapsed(self) -> bool:
        """Check if recovery timeout has elapsed."""
        elapsed = time.time() - self._state.last_failure_time
        return elapsed >= self.config.recovery_timeout

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

            metrics = SelfMetrics.get_instance()
            if self._state.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker transitioning to CLOSED after successful test")
                self._state.state = CircuitState.CLOSED
                metrics.record_circuit_breaker_transition("half_open", "closed")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.CLOSED)
            self._state.failure_count = 0
            self._state.half_open_calls = 0
            metrics.set_circuit_breaker_failure_count(0)

    def _record_failure(self) -> None:
        """Record a failed execution."""
        with self._state.lock:
            previous_state = self._state.state
            self._state.failure_count += 1
            self._state.last_failure_time = time.time()

            metrics = SelfMetrics.get_instance()
            metrics.set_circuit_breaker_failure_count(self._state.failure_count)

            if self._state.state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker transitioning to OPEN after failed test")
                self._state.state = CircuitState.OPEN
                metrics.record_circuit_breaker_transition("half_open", "open")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.OPEN)
            elif self._state.failure_count >= self.config.failure_threshold:
                logger.warning("Circuit breaker transitioning to OPEN after %d failures", self._state.failure_count)
                self._state.state = CircuitState.OPEN
                from_state = "closed" if previous_state == CircuitState.CLOSED else previous_state.value
                metrics.record_circuit_breaker_transition(from_state, "open")
                metrics.set_circuit_breaker_state(CircuitBreakerStateValue.OPEN)

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._state.lock:
            self._state.state = CircuitState.CLOSED
            self._state.failure_count = 0
            self._state.last_failure_time = 0.0
            self._state.half_open_calls = 0
            # Update metrics to reflect reset state
            metrics = SelfMetrics.get_instance()
            metrics.set_circuit_breaker_state(CircuitBreakerStateValue.CLOSED)
            metrics.set_circuit_breaker_failure_count(0)
            logger.info("Circuit breaker reset to CLOSED")
