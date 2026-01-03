"""Factory for creating authenticated router client instances."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter

from ..core.exceptions import handle_auth_error
from ..utils.logging import mask_sensitive_data

if TYPE_CHECKING:
    from .router_client import RouterClient

logger = logging.getLogger(__name__)

ASUS_CLIENT_DEFAULT_HEADERS = {"User-Agent": "asusrouter-Android-DUTUtil-1.0.0.245"}
DEFAULT_TIMEOUT = 10
DEFAULT_REAUTH_INTERVAL = 1800  # 30 minutes in seconds


def create_session() -> requests.Session:
    """
    Create a requests Session with urllib3 retries disabled.

    By default, urllib3 retries failed connections multiple times before
    raising an exception. This causes excessive log spam ("Max retries exceeded")
    and delays when the router is unavailable. We disable these retries so that:

    1. Connection failures are reported immediately
    2. Application-level retry logic (CompositeErrorHandler with RetryHandler
       and CircuitBreaker) handles retries appropriately
    3. Log output is clean and actionable

    Returns:
        Configured requests.Session with no automatic retries
    """
    session = requests.Session()
    # Mount adapters with max_retries=0 to disable urllib3's retry mechanism
    adapter = HTTPAdapter(max_retries=0)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def authenticate_session(host: str, token: str, session: requests.Session | None = None) -> requests.Session:
    """
    Authenticate with the router and return an authenticated session.

    This is the core authentication logic used by both initial authentication
    (RouterClientFactory.auth) and re-authentication (RouterClient._reauthenticate).

    Args:
        host: Router host URL (e.g., "http://192.168.1.1")
        token: Base64-encoded authentication token
        session: Optional existing session to use. If None, creates a new session.

    Returns:
        Authenticated requests.Session

    Raises:
        CaptchaRequiredError: If CAPTCHA is required
        InvalidCredentialsError: If credentials are invalid
        AccountLockedError: If account is locked
        AuthenticationBlockedError: For other auth errors

    Note:
        If a session is provided by the caller and authentication fails,
        the session is NOT closed - the caller retains ownership.
        Only sessions created by this function are closed on failure.
    """
    # Track whether we created the session (for cleanup on failure)
    session_created = session is None
    if session_created:
        session = create_session()

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = f"login_authorization={token}"
    url = f"{host}/login.cgi"

    try:
        masked_payload = mask_sensitive_data(payload)
        logger.debug("Request: POST %s | Data: %s", url, masked_payload)
        response = session.post(
            url, headers={**ASUS_CLIENT_DEFAULT_HEADERS, **headers}, data=payload, timeout=DEFAULT_TIMEOUT
        )
        masked_body = mask_sensitive_data(response.text)
        logger.debug("Response: %s %s | Body: %s", response.status_code, response.url, masked_body[:2000])
        response.raise_for_status()

        # Check for auth error in response (login.cgi returns JSON with error_status on failure)
        try:
            data = response.json()
            if "error_status" in data:
                handle_auth_error(data)
        except (json.JSONDecodeError, ValueError):
            # Success - login.cgi returns non-JSON on successful login
            pass

        return session
    except Exception:
        # Only close the session if we created it; caller retains ownership otherwise
        if session_created:
            session.close()
        raise


class RouterClientFactory:
    """Factory for creating authenticated RouterClient instances."""

    def __init__(self, host: str, reauth_interval: int = DEFAULT_REAUTH_INTERVAL) -> None:
        """
        Initialize the factory.

        Args:
            host: Router hostname or IP address. Will be prefixed with http://
                  if no protocol is specified.
            reauth_interval: Proactive re-authentication interval in seconds.
                             Default is 1800 (30 minutes). Set to 0 to disable.

        Raises:
            ValueError: If reauth_interval is negative.
        """
        if reauth_interval < 0:
            raise ValueError(f"reauth_interval must be non-negative, got {reauth_interval}")

        # Default to HTTP for local network router access. ASUS routers typically
        # don't have HTTPS certificates by default. Users can explicitly specify
        # https:// if their router is configured with SSL/TLS.
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"

        self.host = host.rstrip("/")
        self.reauth_interval = reauth_interval

    def auth(self, auth: str) -> RouterClient:
        """
        Authenticate with the router and create a client.

        Args:
            auth: Authentication string in format "username:password"

        Returns:
            Authenticated RouterClient instance

        Raises:
            CaptchaRequiredError: If CAPTCHA is required
            InvalidCredentialsError: If credentials are invalid
            AccountLockedError: If account is locked
            AuthenticationBlockedError: For other auth errors
        """
        # Import here to avoid circular import
        from .router_client import RouterClient

        token = base64.b64encode(auth.encode("utf-8")).decode("utf-8")
        session = authenticate_session(self.host, token)

        try:
            return RouterClient(
                self.host,
                session,
                _auth_token=token,
                _last_auth_time=time.monotonic(),
                _reauth_interval_seconds=self.reauth_interval,
            )
        except Exception:
            # If RouterClient construction fails, close the session to prevent leak
            session.close()
            raise
