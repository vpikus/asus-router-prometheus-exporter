"""
Custom exceptions for the ASUS Router Exporter.
"""

from __future__ import annotations


class ExporterError(Exception):
    """Base exception for all exporter errors."""

    pass


class ConfigurationError(ExporterError):
    """Raised when there's a configuration error."""

    pass


class AuthenticationError(ExporterError):
    """Raised when authentication with the router fails."""

    pass


class RouterConnectionError(ExporterError):
    """Raised when connection to the router fails."""

    pass


class CollectorError(ExporterError):
    """Raised when a collector encounters an error."""

    def __init__(self, collector_name: str, message: str):
        self.collector_name = collector_name
        super().__init__(f"[{collector_name}] {message}")


class CircuitBreakerOpenError(ExporterError):
    """Raised when circuit breaker is open and blocking requests."""

    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)


class RetryExhaustedError(ExporterError):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Failed after {attempts} attempts. Last error: {last_error}")
