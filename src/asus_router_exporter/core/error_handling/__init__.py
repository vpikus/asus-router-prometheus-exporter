"""
Error handling strategies for the ASUS Router Exporter.

Provides:
- RetryHandler: Retry with exponential backoff
- CircuitBreaker: Fail-fast pattern for fault tolerance
- CompositeErrorHandler: Combines both strategies
"""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitState,
)
from .composite import CompositeErrorHandler
from .retry import RetryConfig, RetryHandler

__all__ = [
    # Retry
    "RetryConfig",
    "RetryHandler",
    # Circuit Breaker
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "CircuitBreaker",
    # Composite
    "CompositeErrorHandler",
]
