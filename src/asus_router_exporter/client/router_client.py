"""HTTP client for ASUS router web API."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, TypeVar, cast

import requests

from ..core.exceptions import (
    AuthenticationError,
    SessionExpiredError,
    handle_auth_error,
)
from ..metrics.self_metrics import SelfMetrics
from ..utils.logging import SensitiveFormatter, mask_sensitive_data
from ..utils.parsing import (
    ids_for,
    int_or_none,
    is_valid_mac,
    parse_hex,
    safe_int,
    to_bool,
    trim_to_none,
)
from .decorators import track_api
from .factory import ASUS_CLIENT_DEFAULT_HEADERS, DEFAULT_TIMEOUT, authenticate_session
from .models import (
    BaseClientInfo,
    ClientAmeshInfo,
    ClientAmeshRole,
    ClientInfo,
    ClientInterface,
    ClientInternetMode,
    ClientInternetState,
    ClientIpMethod,
    ClientOperationMode,
    CpuInfo,
    DslInfo,
    DslTransMode,
    DualWanInfo,
    DualWanOrigin,
    LanInfo,
    LanProtoType,
    LanState,
    LinkInternet,
    MemoryInfo,
    NetdevInfo,
    NetworkWanInfo,
    PortCapability,
    PortInfo,
    QosType,
    RebootScheduleConf,
    RebootScheduleInfo,
    RouterFeatureCapabilities,
    RouterInfo,
    SwMode,
    TemperatureInfo,
    ThroughputInfo,
    TrafficStats,
    UptimeInfo,
    UsbDeviceType,
    WanAuxState,
    WanConnectionInfo,
    WanDslProtoType,
    WanInfo,
    WanMode,
    WanProtoType,
    WanState,
    WanStatus,
    WanSubState,
    WifiAuthMode,
    WifiBand,
    WifiBandInfo,
    WifiCrypto,
    WifiInfo,
    WifiMfp,
    WifiMode,
    WifiUnit,
    WifiWpsWep,
)

# Type variable for generic return type in _request_with_reauth
_T = TypeVar("_T")

# Configure logger with SensitiveFormatter to ensure credentials are masked
# even when this module is used standalone (without asus_router_prometheus.py).
# Note: The lock below is technically redundant since Python's import machinery
# already serializes module-level code. However, it provides explicit safety
# against potential edge cases and documents the thread-safety intent.
logger = logging.getLogger(__name__)
_logger_lock = threading.Lock()
with _logger_lock:
    if not logger.handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(_handler)
        logger.propagate = False  # Prevent duplicate logs if parent also has handlers


@dataclass
class RouterClient:
    """
    HTTP client for ASUS router web API.

    Threading Model:
        This client is NOT thread-safe. Session replacement during re-authentication
        (in _reauthenticate) is not atomic, and concurrent calls from multiple threads
        may encounter stale or closed sessions.

        In this application, this is safe because:
        - The main thread owns the RouterClient and runs all collection operations
        - The Prometheus HTTP server thread only reads metric values (thread-safe at
          the prometheus_client level), never the RouterClient

        If you need to use this client from multiple threads, wrap calls in a Lock
        or create separate client instances per thread.

    Caching:
        To optimize API calls, frequently-called methods that return stable data
        within a collection cycle are cached. Call `clear_cache()` at the start
        of each collection cycle to ensure fresh data.

        Cached methods: get_supported_features(), get_sw_mode(), get_dual_wan_info(),
        get_uptime()

    Proactive Re-authentication:
        To prevent session expiry during long-running operation, the client can
        proactively re-authenticate before the session expires. Configure via
        `reauth_interval_seconds` (default: 1800 = 30 minutes, 0 = disabled).
        Call `check_and_reauthenticate()` at the start of each collection cycle.
    """

    host: str
    session: requests.Session
    _auth_token: str = ""
    _cache: dict[str, Any] = field(default_factory=dict)
    _last_auth_time: float | None = field(default=None)  # monotonic time of last auth
    _reauth_interval_seconds: int = field(default=1800)

    def close(self) -> None:
        """Close the underlying session and release resources."""
        self.clear_cache()
        if self.session is not None:
            self.session.close()

    def clear_cache(self) -> None:
        """Clear the per-cycle cache.

        Should be called at the start of each collection cycle to ensure
        fresh data is fetched from the router.
        """
        self._cache.clear()

    def needs_reauthentication(self) -> bool:
        """Check if proactive re-authentication is needed.

        Returns:
            True if re-authentication interval has elapsed, False otherwise.
            Always returns False if proactive re-auth is disabled (interval=0)
            or no auth token is stored.

        Note:
            Uses monotonic time (time.monotonic) to avoid issues with clock
            changes (NTP sync, manual adjustment, daylight saving, etc.).
        """
        # Disabled if interval is 0 or no token
        if self._reauth_interval_seconds <= 0 or not self._auth_token:
            return False

        # No auth time recorded (shouldn't happen in normal use)
        if self._last_auth_time is None:
            return True

        elapsed = time.monotonic() - self._last_auth_time
        return elapsed >= self._reauth_interval_seconds

    def check_and_reauthenticate(self) -> bool:
        """Proactively re-authenticate if the configured interval has elapsed.

        This should be called at the start of each collection cycle to prevent
        session expiry during long-running operations.

        Returns:
            True if re-authentication was performed, False otherwise.

        Raises:
            SessionExpiredError: If re-authentication fails but can be retried
            CaptchaRequiredError: If CAPTCHA is required
            InvalidCredentialsError: If credentials are invalid
            AccountLockedError: If account is locked
            AuthenticationBlockedError: For other auth errors
        """
        if not self.needs_reauthentication():
            return False

        logger.info(
            "Proactive re-authentication triggered (interval: %ds)",
            self._reauth_interval_seconds,
        )
        self._reauthenticate()
        SelfMetrics.get_instance().record_proactive_reauth()
        return True

    def _get_cached(self, cache_key: str) -> Any | None:
        """
        Get cached value and record hit/miss metrics.

        Args:
            cache_key: The cache key to look up

        Returns:
            Cached value or None if not found
        """
        cached = self._cache.get(cache_key)
        metrics = SelfMetrics.get_instance()
        if cached is not None:
            metrics.record_cache_hit(cache_key)
        else:
            metrics.record_cache_miss(cache_key)
        return cached

    def __enter__(self) -> RouterClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - closes session."""
        self.close()

    def _reauthenticate(self) -> None:
        """Re-authenticate with the router to get a new session.

        Raises:
            SessionExpiredError: If re-authentication fails but can be retried
            CaptchaRequiredError: If CAPTCHA is required
            InvalidCredentialsError: If credentials are invalid
            AccountLockedError: If account is locked
            AuthenticationBlockedError: For other auth errors
        """
        if not self._auth_token:
            raise SessionExpiredError("Cannot re-authenticate: no auth token stored")

        logger.info("Re-authenticating with router...")

        # Use shared authentication logic
        new_session = authenticate_session(self.host, self._auth_token)

        # Close old session before replacing with new one to prevent resource leak
        old_session = self.session
        self.session = new_session
        old_session.close()
        self.clear_cache()  # Invalidate cache to prevent stale data after re-auth
        self._last_auth_time = time.monotonic()  # Track auth time for proactive re-auth
        logger.info("Re-authentication successful")

    def _handle_response(self, response: requests.Response) -> str:
        """
        Handle API response - log and check HTTP status.

        JSON parsing and auth error detection are NOT done here to avoid
        double parsing. Callers must use appropriate methods:
        - _parse_json_response(): For JSON endpoints (validates auth errors)
        - _check_for_error_response(): For non-JSON endpoints that need auth check

        Args:
            response: The HTTP response to handle

        Returns:
            Response text

        Raises:
            HTTPError: If HTTP status indicates an error
        """
        # Mask sensitive data BEFORE truncating to prevent partial field leakage
        masked_body = mask_sensitive_data(response.text)
        logger.debug("Response: %s %s | Body: %s", response.status_code, response.url, masked_body[:2000])
        response.raise_for_status()
        # Note: JSON parsing and error checking is NOT done here to avoid double parsing.
        # Callers should use _parse_json_response() for JSON endpoints, which validates
        # for auth errors. Non-JSON endpoints use _check_for_error_response() if needed.
        return response.text

    @staticmethod
    def _handle_auth_error(data: dict) -> None:
        """
        Handle authentication error response from router.

        This is a wrapper around the shared handle_auth_error function
        that adds logging for authentication errors.

        Args:
            data: Parsed JSON response containing error_status

        Raises:
            CaptchaRequiredError: If captcha_on=1
            SessionExpiredError: If error_status is 1 or 2 and captcha_on=0 (recoverable)
            InvalidCredentialsError: If error_status is 3 or 7
            AccountLockedError: If error_status is 11
            AuthenticationBlockedError: For other error statuses
        """
        # Log auth errors before delegating to shared handler
        error_status = safe_int(data.get("error_status"))
        captcha_on = safe_int(data.get("captcha_on"))

        if captcha_on == 1 or error_status != 0:
            logger.warning(
                "Authentication error from router: error_status=%d, captcha_on=%d",
                error_status,
                captcha_on,
            )

        # Use shared handler with safe_int for type conversion
        handle_auth_error(data, safe_int_func=safe_int)

    def _check_for_error_response(self, response_text: str) -> None:
        """
        Check if response contains an error indicator and raise appropriate exception.

        Use this for non-JSON endpoints (like ajax_coretmp.asp) that normally return
        non-JSON responses but may return JSON error responses when auth fails.

        Args:
            response_text: Raw response text from router

        Raises:
            SessionExpiredError: If session expired (error_status 1-2)
            CaptchaRequiredError: If CAPTCHA is required (captcha_on=1)
            InvalidCredentialsError: If credentials are invalid (error_status 3, 7)
            AccountLockedError: If account is locked (error_status 11)
            AuthenticationBlockedError: For other auth errors (error_status 4-10, 12+)
        """
        try:
            data = json.loads(response_text)
            if isinstance(data, dict) and "error_status" in data:
                self._handle_auth_error(data)
        except json.JSONDecodeError:
            pass  # Not valid JSON - expected for non-JSON endpoints

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        """
        Parse JSON response and validate for authentication errors.

        Use this method instead of json.loads() to ensure error responses
        are properly detected and handled. The router may return error responses
        like {"error_status":"2", "captcha_on":"0"} for any API call when
        the session expires or authentication fails.

        Args:
            response_text: Raw response text from router

        Returns:
            Parsed JSON data as dictionary

        Raises:
            json.JSONDecodeError: If response is not valid JSON
            SessionExpiredError: If session expired (error_status 1-2)
            CaptchaRequiredError: If CAPTCHA is required (captcha_on=1)
            InvalidCredentialsError: If credentials are invalid (error_status 3, 7)
            AccountLockedError: If account is locked (error_status 11)
            AuthenticationBlockedError: For other auth errors (error_status 4-10, 12+)
            ValueError: If response is valid JSON but not a dict
        """
        data = json.loads(response_text)
        if isinstance(data, dict):
            if "error_status" in data:
                self._handle_auth_error(data)
            return data
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    def __get_hook(self, name: str, args: str = "") -> str:
        return self._request_with_reauth(self.__get_hook_impl, name, args)

    def __get_hook_impl(self, name: str, args: str = "") -> str:
        url = f"{self.host}/appGet.cgi"
        params = {"hook": f"{name}({args})"}
        logger.debug("Request: GET %s | Params: %s", url, params)
        response = self.session.get(url, params=params, headers=ASUS_CLIENT_DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
        return self._handle_response(response)

    def __get_nvram(self, *nvrams: str) -> dict[str, Any]:
        return self._request_with_reauth(self.__get_nvram_impl, *nvrams)

    def __get_nvram_impl(self, *nvrams: str) -> dict[str, Any]:
        def __nvramget(*vars_: str) -> str:
            return ";".join(f"nvram_get({v})" for v in vars_)

        url = f"{self.host}/appGet.cgi"
        params = {"hook": f"{__nvramget(*nvrams)}"}
        logger.debug("Request: GET %s | Params: %s", url, params)
        response = self.session.get(url, params=params, headers=ASUS_CLIENT_DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)

        text = self._handle_response(response)
        return self._parse_json_response(text)

    def _request_with_reauth(self, func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        """
        Execute a request function with automatic re-authentication on session expiry.

        Only attempts re-authentication for recoverable errors (SessionExpiredError).
        Non-recoverable errors (invalid credentials, CAPTCHA required, account locked)
        are propagated immediately to prevent account lockout.

        Args:
            func: The request function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The result of the function

        Raises:
            SessionExpiredError: If re-authentication also fails
            CaptchaRequiredError: If CAPTCHA is required (not recoverable)
            InvalidCredentialsError: If credentials are invalid (not recoverable)
            AccountLockedError: If account is locked (not recoverable)
            AuthenticationBlockedError: For other auth errors (not recoverable)
        """
        try:
            return func(*args, **kwargs)
        except AuthenticationError as e:
            # Only retry for recoverable errors (session expired)
            if not e.recoverable:
                raise  # Non-recoverable: don't attempt re-auth to prevent lockout
            if not self._auth_token:
                raise  # Can't re-auth without stored token
            self._reauthenticate()
            # Retry once after re-authentication
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as e:
            # Handle HTTP-level auth failures (401/403) that bypass JSON error check
            if e.response is not None and e.response.status_code in (401, 403):
                if not self._auth_token:
                    raise SessionExpiredError("HTTP authentication failed (no token)") from e
                self._reauthenticate()
                return func(*args, **kwargs)
            raise

    # -------------------------------------------------------------------------
    # System API methods
    # -------------------------------------------------------------------------

    @track_api("get_core_temp")
    def get_core_temp(self) -> TemperatureInfo:
        return self._request_with_reauth(self._get_core_temp_impl)

    def _get_core_temp_impl(self) -> TemperatureInfo:
        url = f"{self.host}/ajax_coretmp.asp"
        logger.debug("Request: GET %s", url)
        response = self.session.get(url, headers=ASUS_CLIENT_DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
        payload = self._handle_response(response)
        # Check for auth errors - ajax_coretmp.asp returns JavaScript but may return JSON on auth failure
        self._check_for_error_response(payload)
        pattern = re.compile(r'(\w+)\s*=\s*("?[^";]+"?);')
        parsed = {m.group(1): m.group(2).strip('"') for m in pattern.finditer(payload)}

        cpu_temp_str = parsed.get("curr_cpuTemp")
        if cpu_temp_str is None:
            raise ValueError("Temperature data 'curr_cpuTemp' not found in router response")
        try:
            cpu_temp = float(cpu_temp_str)
        except ValueError as e:
            raise ValueError(f"Invalid temperature value: {cpu_temp_str}") from e
        return TemperatureInfo(cpu=cpu_temp)

    @track_api("get_uptime")
    def get_uptime(self) -> UptimeInfo:
        """Get router uptime information (cached per collection cycle)."""
        cache_key = "uptime"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cast(UptimeInfo, cached)

        response = self.__get_hook("uptime")
        data = self._parse_json_response(response)

        uptime_str = data.get("uptime")
        if not uptime_str:
            raise ValueError("Uptime data not found in router response")

        # Expected format: "Mon, 01 Jan 2024 12:00:00 +0000 (12345 secs since boot)"
        try:
            uptime_raw = uptime_str.split("(")
            if len(uptime_raw) < 2:
                raise ValueError(f"Unexpected uptime format: {uptime_str}")
            systime = datetime.strptime(uptime_raw[0].strip(), "%a, %d %b %Y %H:%M:%S %z")
            boottime = int(uptime_raw[1].split(" ")[0])
        except (ValueError, IndexError) as e:
            raise ValueError(f"Failed to parse uptime: {uptime_str}") from e

        result = UptimeInfo(systime=systime, boottime=boottime)
        self._cache[cache_key] = result
        return result

    @staticmethod
    def _parse_schedule(schedule: str) -> RebootScheduleConf:
        """Parse reboot schedule string from router.

        Args:
            schedule: Schedule string in format "DDDDDDDHHMM" where:
                - D (7 chars): Binary weekday mask (1=enabled)
                - HH (2 chars): Hour (00-23)
                - MM (2 chars): Minute (00-59)

        Returns:
            Parsed schedule configuration

        Raises:
            ValueError: If schedule format is invalid
        """
        if len(schedule) < 11:
            raise ValueError(f"Invalid schedule format: expected at least 11 chars, got {len(schedule)}")
        try:
            mask = int(schedule[:7], 2)
            hh = int(schedule[7:9])
            mm = int(schedule[9:11])
        except ValueError as e:
            raise ValueError(f"Invalid schedule format: {schedule}") from e
        return RebootScheduleConf(weekday_mask=mask, hh=hh, mm=mm)

    def get_reboot_schedule_time(self) -> RebootScheduleInfo | None:
        caps = self.get_supported_features()
        if not caps.is_supported("reboot_schedule"):
            return None
        nvrams = self.__get_nvram("reboot_schedule_enable", "reboot_schedule")
        if not to_bool(nvrams.get("reboot_schedule_enable", "0")):
            return None
        reboot_schedule = self._parse_schedule(nvrams["reboot_schedule"])
        uptime = self.get_uptime()
        systime = uptime.systime
        for delta in range(8):
            day_dt = systime + timedelta(days=delta)
            if reboot_schedule.is_weekday_enabled(day_dt.weekday()):
                candidate = reboot_schedule.set_time(day_dt)
                if delta > 0 or candidate >= systime:
                    until_ms = max(0, int((candidate - systime).total_seconds() * 1000))
                    return RebootScheduleInfo(next_at=candidate, until_ms=until_ms, schedule=reboot_schedule)
        return None

    @track_api("get_cpu_usage")
    def get_cpu_usage(self) -> list[CpuInfo]:
        response = self.__get_hook("cpu_usage")
        # Router returns malformed JSON wrapper: {"cpu_usage":"cpu1_total":"..."}
        # We need to skip the wrapper and extract the embedded object.
        # Find the second quote (start of embedded data) and add "{" prefix.
        data = self._parse_embedded_json(response, "cpu_usage")
        cpu_infos: list[CpuInfo] = []

        cpu_ids = ids_for("cpu", data.keys())

        for cid in cpu_ids:
            prefix = f"cpu{cid}"
            cpu_infos.append(
                CpuInfo(
                    usage=safe_int(data.get(f"{prefix}_usage", 0)),
                    total=safe_int(data.get(f"{prefix}_total", 0)),
                )
            )

        return cpu_infos

    @track_api("get_memory_usage")
    def get_memory_usage(self) -> MemoryInfo:
        response = self.__get_hook("memory_usage")
        # Router returns malformed JSON wrapper: {"memory_usage":"mem_total":"..."}
        # We need to skip the wrapper and extract the embedded object.
        data = self._parse_embedded_json(response, "memory_usage")
        return MemoryInfo(
            total_kb=safe_int(data.get("mem_total", 0)),
            used_kb=safe_int(data.get("mem_used", 0)),
            free_kb=safe_int(data.get("mem_free", 0)),
        )

    def _parse_embedded_json(self, response: str, wrapper_key: str) -> dict[str, Any]:
        """
        Parse embedded JSON from router's malformed wrapper format.

        Router returns data like: {"wrapper_key":"actual_key":"value",...}
        This extracts the embedded object by finding the colon after wrapper_key
        and parsing from there with a leading brace.

        Before parsing, checks if the response is actually an error response
        (valid JSON with error_status) and raises appropriate exception.

        Args:
            response: Raw response text from router
            wrapper_key: The wrapper key to skip (e.g., "cpu_usage", "memory_usage")

        Returns:
            Parsed JSON dict

        Raises:
            ValueError: If response format is invalid
            SessionExpiredError: If session expired (error_status 1-2)
            CaptchaRequiredError: If CAPTCHA is required (captcha_on=1)
            InvalidCredentialsError: If credentials are invalid (error_status 3, 7)
            AccountLockedError: If account is locked (error_status 11)
            AuthenticationBlockedError: For other auth errors (error_status 4-10, 12+)
        """
        # Check if response is actually an error response (valid JSON with error_status)
        # before attempting to parse as embedded format
        self._check_for_error_response(response)

        # Find the wrapper key and the colon after it
        key_pattern = f'"{wrapper_key}":'
        key_pos = response.find(key_pattern)
        if key_pos == -1:
            raise ValueError(f"Invalid response: wrapper key '{wrapper_key}' not found")

        # Skip past the wrapper key and colon to get the embedded content
        # The response format is: {"wrapper_key":"content...}
        # We need to extract "content" and remove the trailing wrapper brace
        content_start = key_pos + len(key_pattern)
        embedded_content = response[content_start:].rstrip()

        # Remove exactly one trailing "}" (the wrapper closing brace)
        # Using [:-1] instead of rstrip("}") to avoid removing multiple braces
        # which would corrupt nested JSON objects
        if not embedded_content.endswith("}"):
            raise ValueError(f"Invalid response format: expected trailing '}}' in '{wrapper_key}' content")
        embedded_content = embedded_content[:-1]

        # Add braces to make it valid JSON and parse
        try:
            data = json.loads("{" + embedded_content + "}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse embedded JSON for '{wrapper_key}': {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"Expected embedded JSON object for '{wrapper_key}', got {type(data).__name__}")
        return data

    # -------------------------------------------------------------------------
    # Router info API methods
    # -------------------------------------------------------------------------

    @track_api("get_info")
    def get_info(self) -> RouterInfo:
        nvrams = self.__get_nvram(
            "productid",
            "lan_hwaddr",
            "lan_hostname",
            "odmpid",
            "hardware_version",
            "bl_version",
            "svc_ready",
            "qos_enable",
            "bwdpi_app_rulelist",
            "qos_type",
            "firmver",
            "extendno",
            "territory_code",
            "re_mode",
            "serial_no",
            "webs_state_flag",
        )

        sw_mode = self.get_sw_mode()
        caps = self.get_supported_features()
        uptime = self.get_uptime()
        reboot_schedule = self.get_reboot_schedule_time()
        software_update_available = nvrams["webs_state_flag"] in ["1", "2"]
        ports_info = self.get_port_status_infos(nvrams["lan_hwaddr"])

        return RouterInfo(
            product_id=nvrams["productid"],
            lan_hwaddr=nvrams["lan_hwaddr"],
            lan_hostname=nvrams["lan_hostname"],
            odmpid=nvrams["odmpid"],
            hardware_version=nvrams["hardware_version"],
            bl_version=nvrams["bl_version"],
            sw_mode=sw_mode,
            svc_ready=to_bool(nvrams.get("svc_ready", "0")),
            qos_enable=to_bool(nvrams.get("qos_enable", "0")),
            bwdpi_app_rulelist=nvrams["bwdpi_app_rulelist"].replace("&#60", "<"),
            qos_type=QosType(int(nvrams["qos_type"])) if nvrams["qos_type"] != "" else None,
            firmver=nvrams["firmver"],
            extendno=nvrams["extendno"],
            territory_code=nvrams["territory_code"],
            re_mode=to_bool(nvrams["re_mode"]),
            caps=caps,
            uptime=uptime,
            serial_no=nvrams["serial_no"],
            reboot_schedule=reboot_schedule,
            software_update_available=software_update_available,
            ports_info=ports_info,
        )

    @track_api("get_supported_features")
    def get_supported_features(self) -> RouterFeatureCapabilities:
        """Get router feature capabilities (cached per collection cycle)."""
        cache_key = "supported_features"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cast(RouterFeatureCapabilities, cached)

        response = self.__get_hook("get_ui_support")
        data = self._parse_json_response(response)
        cap = RouterFeatureCapabilities(data["get_ui_support"])
        self._cache[cache_key] = cap
        return cap

    @track_api("get_sw_mode")
    def get_sw_mode(self) -> SwMode:
        """Get router software mode (cached per collection cycle)."""
        cache_key = "sw_mode"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cast(SwMode, cached)

        nvrams = self.__get_nvram("sw_mode", "wlc_psta", "wlc_express")
        sw_mode = int(nvrams["sw_mode"])
        wlc_psta = safe_int(nvrams.get("wlc_psta", 0))
        wlc_express = safe_int(nvrams.get("wlc_express", 0))

        mode = SwMode.RT
        if ((sw_mode == 2 and wlc_psta == 0) or (sw_mode == 3 and wlc_psta == 2)) and wlc_express == 0:
            # Repeater
            mode = SwMode.RE
        elif sw_mode == 3 and wlc_psta == 0:
            # Access Point
            mode = SwMode.AP
        elif (sw_mode == 3 and wlc_psta in (1, 3) and wlc_express == 0) or (
            sw_mode == 2 and wlc_psta == 1 and wlc_express == 0
        ):
            # Media Bridge
            mode = SwMode.MB
        elif sw_mode == 2 and wlc_psta == 0 and wlc_express == 1:
            # ExpressWay 2G
            mode = SwMode.EW2
        elif sw_mode == 2 and wlc_psta == 0 and wlc_express == 2:
            # ExpressWay 5G
            mode = SwMode.EW5
        elif sw_mode == 5:
            # Hotspot
            mode = SwMode.HS

        self._cache[cache_key] = mode
        return mode

    # -------------------------------------------------------------------------
    # Network API methods
    # -------------------------------------------------------------------------

    @track_api("get_netdev")
    def get_netdev(self) -> NetdevInfo:
        response = self.__get_hook("netdev", "appobj")
        data = self._parse_json_response(response)
        netdev = data["netdev"]

        bridge = ThroughputInfo(
            total_upload_bytes=parse_hex(netdev["BRIDGE_tx"]), total_download_bytes=parse_hex(netdev["BRIDGE_rx"])
        )

        wired = ThroughputInfo(
            total_upload_bytes=parse_hex(netdev["WIRED_tx"]), total_download_bytes=parse_hex(netdev["WIRED_rx"])
        )

        internet_ids = ids_for("INTERNET", netdev.keys())
        internet: dict[str, ThroughputInfo] = {
            iid: ThroughputInfo(
                total_upload_bytes=parse_hex(netdev.get(f"INTERNET{iid}_tx")),
                total_download_bytes=parse_hex(netdev.get(f"INTERNET{iid}_rx")),
            )
            for iid in internet_ids
        }

        wireless_ids = ids_for("WIRELESS", netdev.keys())
        wireless: dict[str, ThroughputInfo] = {
            wid: ThroughputInfo(
                total_upload_bytes=parse_hex(netdev.get(f"WIRELESS{wid}_tx")),
                total_download_bytes=parse_hex(netdev.get(f"WIRELESS{wid}_rx")),
            )
            for wid in wireless_ids
        }

        return NetdevInfo(bridge=bridge, internet=internet, wired=wired, wireless=wireless)

    # -------------------------------------------------------------------------
    # WAN API methods
    # -------------------------------------------------------------------------

    @track_api("get_dual_wan_info")
    def get_dual_wan_info(self) -> DualWanInfo:
        """Get dual WAN configuration (cached per collection cycle)."""
        cache_key = "dual_wan_info"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cast(DualWanInfo, cached)

        nvrams = self.__get_nvram("wans_dualwan", "wan0_enable", "wan1_enable", "wans_mode")
        wan_unit_response = self.__get_hook("get_wan_unit")
        active_wan_unit = safe_int(self._parse_json_response(wan_unit_response).get("get_wan_unit", 0))
        caps = self.get_supported_features()

        wans_dualwan_raw = nvrams.get("wans_dualwan", "").split()
        wans_dualwan: dict[int, DualWanOrigin] = {
            i: DualWanOrigin(part.lower()) if part.lower() in DualWanOrigin._value2member_map_ else DualWanOrigin.NONE
            for i, part in enumerate(wans_dualwan_raw)
        }

        dualwan_enabled = caps.is_supported("dualwan") and DualWanOrigin.NONE not in set(wans_dualwan.values())
        # Default to FAIL_OVER mode if wans_mode not provided
        wans_mode_str = nvrams.get("wans_mode", WanMode.FAIL_OVER.value)
        result = DualWanInfo(
            wan_origins=wans_dualwan,
            wan0_enable=to_bool(nvrams.get("wan0_enable", "0")),
            wan1_enable=to_bool(nvrams.get("wan1_enable", "0")),
            active_wan_unit=active_wan_unit,
            enabled=dualwan_enabled,
            wans_mode=WanMode(wans_mode_str),
        )
        self._cache[cache_key] = result
        return result

    def get_wan_connection_info(self, wan_index: int = 0) -> WanConnectionInfo:
        nvrams = self.__get_nvram(
            f"wan{wan_index}_state_t", f"wan{wan_index}_sbstate_t", f"wan{wan_index}_auxstate_t", "link_internet"
        )
        return WanConnectionInfo(
            state=WanState(int(nvrams[f"wan{wan_index}_state_t"])),
            substate=WanSubState(int(nvrams[f"wan{wan_index}_sbstate_t"])),
            auxstate=WanAuxState(int(nvrams[f"wan{wan_index}_auxstate_t"])),
            link_internet=LinkInternet(int(nvrams["link_internet"])),
        )

    def get_dsl_info(self) -> DslInfo:
        nvrams = self.__get_nvram("dsl0_proto", "dslx_transmode")
        return DslInfo(
            proto=WanDslProtoType(nvrams["dsl0_proto"]),
            transmode=DslTransMode(nvrams["dslx_transmode"]),
        )

    def get_wan_info(self, wan_index: int = 0) -> WanInfo:
        dual_wan_info = self.get_dual_wan_info()
        wan_connection_info = self.get_wan_connection_info(wan_index)
        status = WanStatus.CONNECTED if wan_connection_info.is_connected else WanStatus.DISCONNECTED
        if (
            dual_wan_info.enabled
            and dual_wan_info.active_wan_unit != wan_index
            and dual_wan_info.wans_mode in [WanMode.FAIL_BACK, WanMode.FAIL_OVER]
        ):
            status = WanStatus.STANDBY
        wan_info = WanInfo(
            status=status, connection_info=wan_connection_info, active=dual_wan_info.active_wan_unit == wan_index
        )
        caps = self.get_supported_features()
        if status == WanStatus.CONNECTED:
            nvrams = self.__get_nvram(f"wan{wan_index}_ipaddr", f"wan{wan_index}_proto")
            wan_info.ipaddr = nvrams[f"wan{wan_index}_ipaddr"]
            wan_info.proto = WanProtoType(nvrams[f"wan{wan_index}_proto"])
            wan_origin = dual_wan_info.wan_origins[wan_index]
            if caps.is_supported("usbX") and wan_origin == DualWanOrigin.USB:
                wan_info.proto = WanProtoType.USB
            elif caps.is_supported("dsl") and wan_origin == DualWanOrigin.DSL:
                dsl_info = self.get_dsl_info()
                if dsl_info.transmode == DslTransMode.ATM and dsl_info.proto in [
                    WanDslProtoType.IPoA,
                    WanDslProtoType.PPPoA,
                ]:
                    wan_info.proto = WanProtoType(dsl_info.proto.value)
        return wan_info

    @track_api("get_network_wan_info")
    def get_network_wan_info(self) -> NetworkWanInfo:
        sw_mode = self.get_sw_mode()
        nvrams = self.__get_nvram("link_internet")
        network_wan_info = NetworkWanInfo(
            mode=sw_mode,
            link_internet=LinkInternet(int(nvrams["link_internet"])),
        )
        if sw_mode == SwMode.RT:
            network_wan_info.primary_wan = self.get_wan_info(0)
            dual_wan_info = self.get_dual_wan_info()
            network_wan_info.dual_wan_info = dual_wan_info
            if dual_wan_info.enabled:
                network_wan_info.secondary_wan = self.get_wan_info(1)
        elif sw_mode == SwMode.AP:
            nvrams = self.__get_nvram("lan_ipaddr", "lan_proto")
            network_wan_info.lan_info = LanInfo(
                state=LanState.CONNECTED,
                ipaddr=nvrams["lan_ipaddr"],
                proto=LanProtoType(nvrams["lan_proto"]),
            )
        return network_wan_info

    # -------------------------------------------------------------------------
    # Wireless API methods
    # -------------------------------------------------------------------------

    def get_wl_nband_info(self) -> dict[WifiBand, int]:
        response = self.__get_hook("wl_nband_info")
        wl_nband_info = self._parse_json_response(response)["wl_nband_info"]
        wl_nband_array = [int(v) for v in wl_nband_info]
        counts = Counter(wl_nband_array)

        return {band: counts.get(band.value, 0) for band in WifiBand}

    def get_wireless_band_info(self, wl_unit: WifiUnit, repeater: bool) -> WifiBandInfo:
        unit = f"{wl_unit.value}{'.1' if repeater else ''}"
        nvrams = self.__get_nvram(
            f"wl{unit}_mbo_enable",
            f"wl{unit}_ssid",
            f"wl{unit}_nmode_x",
            f"wl{unit}_auth_mode_x",
            f"wl{unit}_crypto",
            f"wl{unit}_mfp",
            f"wl{unit}_wep_x",
            f"wl{unit}_closed",
            f"wl{unit}_hwaddr",
        )
        return WifiBandInfo(
            ssid=nvrams[f"wl{unit}_ssid"],
            mac=nvrams[f"wl{unit}_hwaddr"],
            mode=WifiMode(int(nvrams[f"wl{unit}_nmode_x"])),
            auth_mode=WifiAuthMode(nvrams[f"wl{unit}_auth_mode_x"]),
            crypto=WifiCrypto(nvrams[f"wl{unit}_crypto"]),
            mfp=WifiMfp(int(nvrams[f"wl{unit}_mfp"])),
            wep=WifiWpsWep(int(nvrams[f"wl{unit}_wep_x"])),
            hidden_ssid=to_bool(nvrams[f"wl{unit}_closed"]),
            mbo_enabled=to_bool(nvrams.get(f"wl{unit}_mbo_enable", "0")),
        )

    @track_api("get_wireless_info")
    def get_wireless_info(self) -> WifiInfo:
        wl_nband_info = self.get_wl_nband_info()
        nvrams = self.__get_nvram("wps_enable", "wlc_band", "smart_connect_x")
        wifi_info = WifiInfo(
            bands_count=wl_nband_info,
            wps_enabled=to_bool(nvrams.get("wps_enable", "0")),
            smart_connect_enabled=to_bool(nvrams.get("smart_connect_x", "0")),
        )

        caps = self.get_supported_features()
        sw_mode = self.get_sw_mode()
        wlc_band = nvrams["wlc_band"]
        concurrep_support = caps.is_supported("concurrep")
        if caps.is_supported("2.4G"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_2G))
            wifi_info.band_2G_info = self.get_wireless_band_info(WifiUnit.WL_2G, repeater)
        if caps.is_supported("5G"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_5G))
            wifi_info.band_5G_info = self.get_wireless_band_info(WifiUnit.WL_5G, repeater)
        if caps.is_supported("5G-2"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_5G_2))
            wifi_info.band_5G_2_info = self.get_wireless_band_info(WifiUnit.WL_5G_2, repeater)
        if caps.is_supported("wifi6e"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_6G))
            wifi_info.band_6G_info = self.get_wireless_band_info(WifiUnit.WL_6G, repeater)

        return wifi_info

    # -------------------------------------------------------------------------
    # Ports API methods
    # -------------------------------------------------------------------------

    def get_plugged_usb_devices(self) -> list[UsbDeviceType]:
        response = self.__get_hook("show_usb_path")
        all_usb_statuses = self._parse_json_response(response)["show_usb_path"]
        usb_devices = []
        for usb_status in all_usb_statuses:
            usb_devices.append(UsbDeviceType(usb_status))
        return usb_devices

    @track_api("get_port_status_infos")
    def get_port_status_infos(self, mac: str) -> list[PortInfo]:
        return self._request_with_reauth(self._get_port_status_infos_impl, mac)

    def _get_port_status_infos_impl(self, mac: str) -> list[PortInfo]:
        if not is_valid_mac(mac):
            raise ValueError(f"Invalid MAC address: {mac}")

        url = f"{self.host}/get_port_status.cgi"
        params = {"node_mac": mac}
        logger.debug("Request: GET %s | Params: %s", url, params)
        response = self.session.get(url, params=params, headers=ASUS_CLIENT_DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT)
        response_text = self._handle_response(response)
        data = self._parse_json_response(response_text)

        port_infos: list[PortInfo] = []
        port_info_raw = data.get("port_info", {}).get(mac, {})
        for port_id, port_data in port_info_raw.items():
            port_info = PortInfo(
                id=port_id,
                plugged=to_bool(port_data["is_on"]),
                capability=PortCapability(int(port_data["cap"])),
                max_supported_speed_rate_mbps=int(port_data["max_rate"]),
                current_speed_rate_mbps=int(port_data["link_rate"]),
            )
            port_infos.append(port_info)
        return port_infos

    # -------------------------------------------------------------------------
    # Clients API methods
    # -------------------------------------------------------------------------

    def _map_client_info(self, caps: RouterFeatureCapabilities, client_data, client_db_data) -> ClientInfo:
        op_mode = int(client_data["opMode"])
        ip_method = trim_to_none(client_data["ipMethod"])
        last_conn_ts = int_or_none(client_db_data["conn_ts"])
        interface = ClientInterface.from_code(int(client_data["isWL"])) or ClientInterface.LAN
        last_conn_interface = ClientInterface.from_code(int(client_db_data["is_wireless"])) or ClientInterface.LAN
        client_info = ClientInfo(
            name=client_data["name"],
            nick_name=client_data["nickName"],
            ipaddr=client_data["ip"],
            mac=client_data["mac"],
            vendor=client_data["vendor"],
            interface=interface,
            last_conn_interface=last_conn_interface,
            online=to_bool(client_data["isOnline"]),
            op_mode=ClientOperationMode(op_mode) if op_mode > 0 else None,
            rssi=int_or_none(client_data["rssi"]),
            ip_method=ClientIpMethod(ip_method) if ip_method else None,
            internet_mode=ClientInternetMode(client_data["internetMode"]),
            internet_state=ClientInternetState(to_bool(client_data["internetState"])),
            os_type=safe_int(client_db_data["os_type"]),
            device_type=safe_int(client_db_data["type"]),
            last_conn_ts=last_conn_ts if last_conn_ts is not None and last_conn_ts > 0 else None,
        )
        if caps.is_supported("stainfo"):
            total_tx = int_or_none(client_data["totalTx"])
            total_rx = int_or_none(client_data["totalRx"])
            cur_tx = int_or_none(client_data["curTx"])
            cur_rx = int_or_none(client_data["curRx"])
            client_info.conn_time = trim_to_none(client_data["wlConnectTime"])

            client_info.throughput_info = (
                ThroughputInfo(
                    total_upload_bytes=total_tx,
                    total_download_bytes=total_rx,
                )
                if total_tx and total_rx
                else None
            )

            client_info.traffic_stats = (
                TrafficStats(
                    rx=cur_rx,
                    tx=cur_tx,
                )
                if cur_rx and cur_tx
                else None
            )

        if caps.is_supported("amas"):
            is_re_client = bool(safe_int(client_data.get("amesh_isReClient")))
            is_re = bool(safe_int(client_data.get("amesh_isRe")))
            if is_re_client:
                client_info.amesh_info = ClientAmeshInfo(
                    role=ClientAmeshRole.CLIENT, pap_mac=client_data["amesh_papMac"]
                )
            elif is_re:
                client_info.amesh_info = ClientAmeshInfo(role=ClientAmeshRole.REPEATER)

            if client_info.amesh_info and caps.is_supported("force_roaming") and caps.is_supported("sta_ap_bind"):
                client_info.amesh_info.bind_band = safe_int(client_data["amesh_bind_band"])
                client_info.amesh_info.bind_mac = client_data["amesh_bind_mac"]
        return client_info

    def _map_client_info_from_db(self, caps: RouterFeatureCapabilities, client_db_data) -> BaseClientInfo:
        last_conn_ts = int_or_none(client_db_data["conn_ts"])
        last_conn_interface = ClientInterface.from_code(int(client_db_data["is_wireless"])) or ClientInterface.LAN
        client_info = BaseClientInfo(
            name=client_db_data["name"],
            nick_name=client_db_data["nickName"],
            mac=client_db_data["mac"],
            vendor=client_db_data["vendor"],
            online=to_bool(client_db_data["online"]),
            os_type=safe_int(client_db_data["os_type"]),
            device_type=safe_int(client_db_data["type"]),
            last_conn_ts=last_conn_ts if last_conn_ts is not None and last_conn_ts > 0 else None,
            last_conn_interface=last_conn_interface,
        )

        if caps.is_supported("amas"):
            is_re = to_bool(client_db_data["amesh_isRe"])
            if is_re:
                client_info.amesh_info = ClientAmeshInfo(role=ClientAmeshRole.CLIENT)
            else:
                client_info.amesh_info = ClientAmeshInfo(role=ClientAmeshRole.REPEATER)

            if caps.is_supported("force_roaming") and caps.is_supported("sta_ap_bind"):
                client_info.amesh_info.bind_band = safe_int(client_db_data["amesh_bind_band"])
                client_info.amesh_info.bind_mac = client_db_data["amesh_bind_mac"]

        return client_info

    @track_api("get_clients")
    def get_clients(self) -> list[BaseClientInfo]:
        caps = self.get_supported_features()
        clientlist_response = self.__get_hook("get_clientlist")
        get_clientlist = self._parse_json_response(clientlist_response).get("get_clientlist")
        clientlist_db_response = self.__get_hook("get_clientlist_from_json_database")
        get_clientlist_from_db = self._parse_json_response(clientlist_db_response).get(
            "get_clientlist_from_json_database"
        )
        clients: list[BaseClientInfo] = []
        for client_mac, client_db_data in get_clientlist_from_db.items():
            if not is_valid_mac(client_mac):
                continue

            client_info: BaseClientInfo
            if client_mac in get_clientlist:
                client_data = get_clientlist[client_mac]
                client_info = self._map_client_info(caps, client_data, client_db_data)
            else:
                client_info = self._map_client_info_from_db(caps, client_db_data)
            clients.append(client_info)

        return clients
