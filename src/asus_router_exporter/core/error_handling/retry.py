"""
Retry handler with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...metrics.self_metrics import SelfMetrics
from ..exceptions import AuthenticationError, RetryExhaustedError, RouterConnectionError

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
            AuthenticationError: If a non-recoverable auth error occurs (not retried)
            RouterConnectionError: If a non-recoverable connection error occurs (not retried)

        Note:
            Exceptions with recoverable=False are NOT retried:
            - AuthenticationError subclasses (InvalidCredentialsError, CaptchaRequiredError,
              AccountLockedError, AuthenticationBlockedError) to prevent account lockout.
            - RouterConnectionError (default recoverable=False) because connection failures
              indicate router is unreachable and retrying won't help.
        """
        if not self.config.enabled:
            return func(*args, **kwargs)

        # If retryable_exceptions is empty, no exceptions will be caught and retried.
        # In this case, just execute directly and let any exception propagate.
        if not self.config.retryable_exceptions:
            return func(*args, **kwargs)

        last_error: Exception | None = None
        delay = self.config.initial_delay

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except self.config.retryable_exceptions as e:
                # Don't retry non-recoverable errors - they indicate permanent failures.
                # AuthenticationError: InvalidCredentialsError, CaptchaRequiredError, etc.
                # RouterConnectionError: Router unreachable (retrying won't help).
                if isinstance(e, AuthenticationError) and not e.recoverable:
                    logger.error(
                        "Non-recoverable authentication error (attempt %d/%d): %s. Not retrying.",
                        attempt,
                        self.config.max_attempts,
                        str(e),
                    )
                    raise
                if isinstance(e, RouterConnectionError) and not e.recoverable:
                    logger.error(
                        "Non-recoverable connection error (attempt %d/%d): %s. Not retrying.",
                        attempt,
                        self.config.max_attempts,
                        str(e),
                    )
                    raise

                last_error = e
                if attempt < self.config.max_attempts:
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt,
                        self.config.max_attempts,
                        str(e),
                        delay,
                    )
                    SelfMetrics.get_instance().record_retry_attempt()
                    time.sleep(delay)
                    delay = min(delay * self.config.backoff_factor, self.config.max_delay)
                else:
                    logger.exception("All %d attempts failed", self.config.max_attempts)
                    SelfMetrics.get_instance().record_retries_exhausted()

        # last_error should never be None here since we only reach this point
        # after catching at least one exception, but assert for type safety
        assert last_error is not None, "Unexpected state: no error recorded"
        raise RetryExhaustedError(self.config.max_attempts, last_error)
