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
    """Raised when authentication with the router fails.

    This is the base class for authentication errors. Subclasses indicate
    whether the error is recoverable (can retry authentication) or permanent
    (should stop trying to prevent account lockout).
    """

    def __init__(self, message: str, *, recoverable: bool = True):
        """
        Initialize authentication error.

        Args:
            message: Error description
            recoverable: If True, re-authentication may succeed. If False,
                         the application should stop authentication attempts
                         to prevent account lockout.
        """
        super().__init__(message)
        self.recoverable = recoverable


class SessionExpiredError(AuthenticationError):
    """Raised when the router session has expired (error_status 1 or 2).

    This is a recoverable error - re-authentication should be attempted.
    """

    def __init__(self, message: str = "Router session expired"):
        super().__init__(message, recoverable=True)


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid (error_status 3 or 7).

    This is NOT recoverable - do not retry to prevent account lockout.
    """

    def __init__(self, message: str = "Invalid username or password"):
        super().__init__(message, recoverable=False)


class CaptchaRequiredError(AuthenticationError):
    """Raised when CAPTCHA is required for authentication (captcha_on=1).

    This is NOT recoverable - CAPTCHA must be disabled in router settings.
    """

    def __init__(
        self,
        message: str = "CAPTCHA is required. Please disable CAPTCHA in ASUS Router "
        "settings (Administration -> System -> Enable Web Access from WAN -> Disable CAPTCHA)",
    ):
        super().__init__(message, recoverable=False)


class AccountLockedError(AuthenticationError):
    """Raised when the router account is locked due to too many failed attempts.

    error_status 11 indicates the router is locked and requires factory reset.
    This is NOT recoverable.
    """

    def __init__(
        self,
        message: str = "Router account is locked due to too many failed login attempts. "
        "Manual factory reset required (press reset button on router).",
    ):
        super().__init__(message, recoverable=False)


class AuthenticationBlockedError(AuthenticationError):
    """Raised when authentication is blocked for other reasons (error_status 4-10, 12+).

    This is NOT recoverable - do not retry to prevent further issues.
    """

    ERROR_MESSAGES = {
        4: "Authentication rejected: NOREFERER - request missing required referer header",
        5: "Authentication rejected: REFERERFAIL - invalid referer header",
        8: "Authentication rejected: ISLOGOUT - session logged out",
        9: "Authentication rejected: NOLOGIN - not logged in",
        10: "Authentication rejected: WRONGCAPTCHA - incorrect CAPTCHA",
    }

    def __init__(self, error_status: int, message: str | None = None):
        self.error_status = error_status
        if message is None:
            message = self.ERROR_MESSAGES.get(
                error_status, f"Authentication rejected: unexpected error_status={error_status}"
            )
        super().__init__(message, recoverable=False)


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
