"""
Core components for the ASUS Router Exporter.

Includes configuration, protocols, error handling, and DI container.
"""

from .config import Config
from .container import Container
from .error_handling import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitState,
    CompositeErrorHandler,
    RetryConfig,
    RetryHandler,
)
from .exceptions import (
    AccountLockedError,
    AuthenticationBlockedError,
    AuthenticationError,
    CaptchaRequiredError,
    CircuitBreakerOpenError,
    CollectorError,
    ConfigurationError,
    ExporterError,
    InvalidCredentialsError,
    RetryExhaustedError,
    RouterConnectionError,
    SessionExpiredError,
)
from .protocols import (
    ConfigProviderProtocol,
    ErrorHandlerProtocol,
    MetricCollectorProtocol,
    RouterClientProtocol,
)

__all__ = [
    # Configuration
    "Config",
    # Container
    "Container",
    # Exceptions
    "ExporterError",
    "ConfigurationError",
    "AuthenticationError",
    "SessionExpiredError",
    "InvalidCredentialsError",
    "CaptchaRequiredError",
    "AccountLockedError",
    "AuthenticationBlockedError",
    "RouterConnectionError",
    "CollectorError",
    "CircuitBreakerOpenError",
    "RetryExhaustedError",
    # Error handling
    "RetryConfig",
    "RetryHandler",
    "CircuitState",
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CompositeErrorHandler",
    # Protocols
    "RouterClientProtocol",
    "MetricCollectorProtocol",
    "ConfigProviderProtocol",
    "ErrorHandlerProtocol",
]
