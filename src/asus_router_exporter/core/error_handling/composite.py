"""
Composite error handler combining retry and circuit breaker.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .retry import RetryConfig, RetryHandler


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
        # Use `or {}` to handle case where config value is explicitly None
        # (e.g., YAML with `error_handling: null` or `error_handling:` with no value)
        error_config = config.get("error_handling", {}) or {}
        retry = error_config.get("retry", {}) or {}
        circuit = error_config.get("circuit_breaker", {}) or {}

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
