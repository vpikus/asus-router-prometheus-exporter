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
    """Raised when connection to the router fails.

    Connection errors are not retryable by default because they indicate
    the router is unreachable (network issue, router offline). Retrying
    with short delays won't help and should be avoided to trigger the
    circuit breaker faster.
    """

    def __init__(
        self,
        message: str = "Connection to router failed",
        *,
        recoverable: bool = False,
    ):
        """
        Initialize router connection error.

        Args:
            message: Error description
            recoverable: If True, retry may succeed. If False (default),
                        the error should trigger circuit breaker immediately.
        """
        super().__init__(message)
        self.recoverable = recoverable


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


def handle_auth_error(data: dict, *, safe_int_func: callable = int) -> None:
    """
    Handle authentication error response from router.

    Router returns JSON like:
    {
        "error_status": "2",
        "captcha_on": "0",
        "last_time_lock_warning": "0"
    }

    Error status meanings:
        0: No error
        1: Token is required
        2: Token is expired, new authentication required
        3: Invalid credentials
        4: NOREFERER
        5: REFERERFAIL
        7: Incorrect username/password 5 times
        8: ISLOGOUT
        9: NOLOGIN
        10: WRONGCAPTCHA
        11: Router locked (10 failed attempts, requires factory reset)
        12+: Unexpected errors

    Args:
        data: Parsed JSON response containing error_status
        safe_int_func: Function to safely convert values to int (default: int).
                       Pass a function that returns 0 on ValueError/TypeError
                       for handling empty strings or non-numeric values.

    Raises:
        CaptchaRequiredError: If captcha_on=1
        SessionExpiredError: If error_status is 1 or 2 and captcha_on=0 (recoverable)
        InvalidCredentialsError: If error_status is 3 or 7
        AccountLockedError: If error_status is 11
        AuthenticationBlockedError: For other error statuses
    """

    def _safe_int(value) -> int:
        """Convert value to int, returning 0 on error."""
        try:
            return safe_int_func(value)
        except (ValueError, TypeError):
            return 0

    error_status = _safe_int(data.get("error_status"))
    captcha_on = _safe_int(data.get("captcha_on"))

    # CAPTCHA check takes priority - if CAPTCHA is required, no auth attempt should be made
    if captcha_on == 1:
        raise CaptchaRequiredError(
            f"CAPTCHA is required (error_status={error_status}). "
            "Please disable CAPTCHA in ASUS Router settings "
            "(Administration -> System -> Enable Web Access from WAN -> Disable CAPTCHA)"
        )

    # error_status 0 means no error - return without raising
    if error_status == 0:
        return

    # Recoverable errors (error_status 1 or 2): session expired, can re-authenticate
    if error_status in (1, 2):
        raise SessionExpiredError(f"Router session expired (error_status={error_status})")

    # Invalid credentials (error_status 3 or 7)
    if error_status == 3:
        raise InvalidCredentialsError(f"Invalid credentials provided (error_status={error_status})")
    if error_status == 7:
        raise InvalidCredentialsError(
            f"Incorrect username or password entered 5 times (error_status={error_status}). "
            "Further attempts may lock the account."
        )

    # Account locked (error_status 11)
    if error_status == 11:
        raise AccountLockedError(
            f"Router account is locked due to too many failed login attempts (error_status={error_status}). "
            "Manual factory reset required (press reset button on router)."
        )

    # All other errors (4, 5, 8, 9, 10, 12+) - blocked, non-recoverable
    raise AuthenticationBlockedError(error_status)
