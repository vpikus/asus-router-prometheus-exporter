"""
Error handling strategies for the ASUS Router Exporter.

Provides:
- RetryHandler: Retry with exponential backoff
- CircuitBreaker: Fail-fast pattern for fault tolerance
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

from .exceptions import CircuitBreakerOpenError, RetryExhaustedError

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    enabled: bool = True
    max_attempts: int = 3
    backoff_factor: float = 2.0
    max_delay: float = 30.0
    initial_delay: float = 1.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)


class RetryHandler:
    """
    Retry handler with exponential backoff.

    Example:
        handler = RetryHandler(RetryConfig(max_attempts=3))
        result = handler.execute(my_function, arg1, arg2)
    """

    def __init__(self, config: RetryConfig | None = None):
        """
        Initialize retry handler.

        Args:
            config: Retry configuration (uses defaults if not provided)
        """
        self.config = config or RetryConfig()

    def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Function result

        Raises:
            RetryExhaustedError: If all retry attempts fail
        """
        if not self.config.enabled:
            return func(*args, **kwargs)

        last_error: Exception | None = None
        delay = self.config.initial_delay

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except self.config.retryable_exceptions as e:
                last_error = e
                if attempt < self.config.max_attempts:
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt,
                        self.config.max_attempts,
                        str(e),
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * self.config.backoff_factor, self.config.max_delay)
                else:
                    logger.exception("All %d attempts failed", self.config.max_attempts)

        # last_error should never be None here since we only reach this point
        # after catching at least one exception, but assert for type safety
        assert last_error is not None, "Unexpected state: no error recorded"
        raise RetryExhaustedError(self.config.max_attempts, last_error)


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

            if self._state.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker transitioning to CLOSED after successful test")
                self._state.state = CircuitState.CLOSED
            self._state.failure_count = 0
            self._state.half_open_calls = 0

    def _record_failure(self) -> None:
        """Record a failed execution."""
        with self._state.lock:
            self._state.failure_count += 1
            self._state.last_failure_time = time.time()

            if self._state.state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker transitioning to OPEN after failed test")
                self._state.state = CircuitState.OPEN
            elif self._state.failure_count >= self.config.failure_threshold:
                logger.warning("Circuit breaker transitioning to OPEN after %d failures", self._state.failure_count)
                self._state.state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._state.lock:
            self._state.state = CircuitState.CLOSED
            self._state.failure_count = 0
            self._state.last_failure_time = 0.0
            self._state.half_open_calls = 0
            logger.info("Circuit breaker reset to CLOSED")


class CompositeErrorHandler:
    """
    Combines retry and circuit breaker for robust error handling.

    The circuit breaker wraps the retry handler, so:
    1. Circuit breaker checks if requests should be allowed
    2. Retry handler attempts the operation with backoff
    3. Failures are reported back to the circuit breaker
    """

    def __init__(self, retry_config: RetryConfig | None = None, circuit_config: CircuitBreakerConfig | None = None):
        """
        Initialize composite handler.

        Args:
            retry_config: Configuration for retry behavior
            circuit_config: Configuration for circuit breaker
        """
        self.retry_handler = RetryHandler(retry_config)
        self.circuit_breaker = CircuitBreaker(circuit_config)

    def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute function with combined error handling.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            RetryExhaustedError: If all retries fail
        """

        def retryable_call() -> Any:
            return self.retry_handler.execute(func, *args, **kwargs)

        return self.circuit_breaker.execute(retryable_call)

    @classmethod
    def from_config(cls, config: Any) -> CompositeErrorHandler:
        """
        Create handler from configuration object.

        Args:
            config: Configuration with error_handling section

        Returns:
            Configured CompositeErrorHandler
        """
        error_config = config.get("error_handling", {})
        retry = error_config.get("retry", {})
        circuit = error_config.get("circuit_breaker", {})

        retry_config = RetryConfig(
            enabled=retry.get("enabled", True),
            max_attempts=retry.get("max_attempts", 3),
            backoff_factor=retry.get("backoff_factor", 2.0),
            max_delay=retry.get("max_delay", 30.0),
        )

        circuit_config = CircuitBreakerConfig(
            enabled=circuit.get("enabled", True),
            failure_threshold=circuit.get("failure_threshold", 5),
            recovery_timeout=circuit.get("recovery_timeout", 60.0),
            half_open_max_calls=circuit.get("half_open_max_calls", 3),
        )

        return cls(retry_config, circuit_config)
