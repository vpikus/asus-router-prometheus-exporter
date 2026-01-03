"""Factory for creating authenticated router client instances."""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter

from ..utils.logging import mask_sensitive_data

if TYPE_CHECKING:
    from .router_client import RouterClient

logger = logging.getLogger(__name__)

ASUS_CLIENT_DEFAULT_HEADERS = {"User-Agent": "asusrouter-Android-DUTUtil-1.0.0.245"}
DEFAULT_TIMEOUT = 10


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


class RouterClientFactory:
    """Factory for creating authenticated RouterClient instances."""

    def __init__(self, host: str) -> None:
        # Default to HTTP for local network router access. ASUS routers typically
        # don't have HTTPS certificates by default. Users can explicitly specify
        # https:// if their router is configured with SSL/TLS.
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"

        self.host = host.rstrip("/")

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
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = f"login_authorization={token}"
        # Create session with urllib3 retries disabled - app-level retry handles failures
        session = create_session()
        try:
            url = f"{self.host}/login.cgi"
            # Mask request payload for defense-in-depth (in case handler without SensitiveFormatter is added)
            masked_payload = mask_sensitive_data(payload)
            logger.debug("Request: POST %s | Data: %s", url, masked_payload)
            response = session.post(
                url, headers={**ASUS_CLIENT_DEFAULT_HEADERS, **headers}, data=payload, timeout=DEFAULT_TIMEOUT
            )
            # Mask sensitive data BEFORE truncating to prevent partial field leakage
            masked_body = mask_sensitive_data(response.text)
            logger.debug("Response: %s %s | Body: %s", response.status_code, response.url, masked_body[:2000])
            response.raise_for_status()

            # Check for auth error in response (login.cgi returns JSON with error_status on failure)
            try:
                data = response.json()
                if "error_status" in data:
                    RouterClient._handle_auth_error(data)
            except json.decoder.JSONDecodeError:
                # Success - login.cgi returns non-JSON on successful login
                pass

            return RouterClient(self.host, session, _auth_token=token)
        except Exception:
            session.close()
            raise
