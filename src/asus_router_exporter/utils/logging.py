"""
Logging utilities for ASUS router client with sensitive data masking.

Provides a custom logging.Formatter that automatically masks sensitive
information like IP addresses, MAC addresses, credentials, etc.
"""

from __future__ import annotations

import logging
import re

# Regex patterns for sensitive data
_IPV4_PATTERN = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

# Improved IPv6 pattern covering more formats:
# - Full form: 2001:0db8:85a3:0000:0000:8a2e:0370:7334
# - Compressed: 2001:db8::8a2e:370:7334, ::1, fe80::1
# - IPv4-mapped: ::ffff:192.168.1.1
# - With zone ID: fe80::1%eth0
_IPV4_OCTET = r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'
_IPV4_EMBEDDED = rf'(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET}'
# Note: Alternatives are ordered from most specific to least specific to ensure
# greedy matching. Uses lookbehind/lookahead instead of \b for addresses starting
# or ending with colons, since \b doesn't work well with non-word characters.
_IPV6_PATTERN = re.compile(
    r'(?:(?<=\s)|(?<=^)|(?<=[^\w:]))'  # Lookbehind: start of string, whitespace, or non-word/non-colon
    r'(?:'
    # IPv4-mapped/compatible: ::ffff:192.168.1.1 or ::192.168.1.1
    rf'::(?:[fF]{{4}}:)?{_IPV4_EMBEDDED}|'
    # Full form (8 groups)
    r'(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|'
    # :: in the middle (most specific first - more segments after ::)
    r'[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}|'
    r'(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|'
    # :: at the start (::1, ::1234:5678, etc.)
    r':(?::[0-9a-fA-F]{1,4}){1,7}|'
    # Just :: with optional trailing segments
    r'::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}|'
    # :: at the end (fe80::, 2001:db8::, etc.)
    r'(?:[0-9a-fA-F]{1,4}:){1,7}:|'
    # Just ::
    r'::'
    r')'
    # Optional zone ID (e.g., %eth0, %eth0_1, %wlan0.1, %br-lan)
    r'(?:%[a-zA-Z0-9_.-]+)?'
    r'(?=\s|$|[^\w:%.-])'  # Lookahead: end of string, whitespace, or non-word/non-colon/non-%/non-dot/non-hyphen
)

# MAC address patterns - supports multiple formats:
# - Colon-separated: AA:BB:CC:DD:EE:FF
# - Hyphen-separated: AA-BB-CC-DD-EE-FF
# - Cisco dot notation: 0011.2233.4455
_MAC_PATTERN = re.compile(
    r'\b(?:'
    r'(?:[0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}|'  # Colon or hyphen format
    r'[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}'  # Cisco dot format
    r')\b'
)

# JSON field patterns for sensitive string values
_SENSITIVE_FIELDS = [
    'serial_no',
    'lan_hostname',
    'name',
    'nickName',
    'nick_name',
    'vendor',
    'login_authorization',
    # IP address fields (defense-in-depth)
    'wan0_ipaddr',
    'wan1_ipaddr',
    'lan_ipaddr',
    'ipaddr',
    # MAC address fields (defense-in-depth)
    'lan_hwaddr',
    'amesh_papMac',
    'amesh_bind_mac',
    # Credentials and passwords
    'http_passwd',
    'http_username',
    # PPPoE credentials
    'wan_pppoe_passwd',
    'wan0_pppoe_passwd',
    'wan1_pppoe_passwd',
    'wan_pppoe_username',
    'wan0_pppoe_username',
    'wan1_pppoe_username',
    # VPN credentials
    'vpn_server_password',
    'vpn_client_password',
    # DDNS credentials
    'ddns_passwd',
    'ddns_username',
    # Session tokens
    'asus_token',
    'login_token',
]

# Pattern fragment to match JSON string values including escaped quotes
# Matches: any char except quote/backslash, OR any escaped char (backslash + any char)
_JSON_STRING_VALUE = r'(?:[^"\\]|\\.)*'

# Pre-compile patterns for sensitive fields (performance optimization)
# Handles escaped quotes in JSON values (e.g., "name": "John\"Doe")
_SENSITIVE_FIELD_PATTERNS = {
    field: re.compile(rf'("{re.escape(field)}"\s*:\s*")({_JSON_STRING_VALUE})"')
    for field in _SENSITIVE_FIELDS
}

# WiFi PSK pattern (wl*_wpa_psk fields) - matches wl0_wpa_psk, wl1_wpa_psk, wl0.1_wpa_psk, etc.
_WPA_PSK_FIELD_PATTERN = re.compile(rf'("wl[0-9]+(?:\.[0-9]+)?_wpa_psk"\s*:\s*")({_JSON_STRING_VALUE})"')

# SSID pattern (wl*_ssid fields) - matches wl0_ssid, wl1_ssid, wl0.1_ssid, etc.
_SSID_FIELD_PATTERN = re.compile(rf'("wl[0-9]+(?:\.[0-9]+)?_ssid"\s*:\s*")({_JSON_STRING_VALUE})"')

# Login authorization in form data - includes % for URL-encoded tokens
_AUTH_PATTERN = re.compile(r'login_authorization=([A-Za-z0-9+/=%]+)')

# Non-sensitive IPs to preserve
_NON_SENSITIVE_IPS = frozenset({'0.0.0.0', '255.255.255.255', '127.0.0.1', '::', '::1'})


def _mask_string(value: str, visible_chars: int = 2) -> str:
    """Mask a string, keeping only first few characters visible."""
    if len(value) <= visible_chars:
        return '*' * len(value)
    return value[:visible_chars] + '*' * (len(value) - visible_chars)


def _mask_ip(ip: str) -> str:
    """Mask an IP address, keeping only first octet/segment visible."""
    # Remove zone ID if present (e.g., %eth0)
    ip_clean = ip.split('%')[0]
    # IPv4-mapped IPv6 (e.g., ::ffff:192.168.1.1) - mask as IPv6
    if ip_clean.startswith('::') and '.' in ip_clean:
        return '::****:*.*.*'
    if '.' in ip_clean and ':' not in ip_clean:
        # Pure IPv4: show first octet
        parts = ip_clean.split('.')
        return parts[0] + '.*.*.*'
    else:
        # IPv6: show first segment
        parts = ip_clean.split(':')
        first_segment = parts[0] if parts[0] else '0'
        return first_segment + ':****:****:****'


def _mask_mac(mac: str) -> str:
    """Mask a MAC address, keeping vendor prefix (first 3 octets) visible."""
    # Handle Cisco dot format (0011.2233.4455)
    if '.' in mac:
        parts = mac.split('.')
        if len(parts) == 3:
            # Keep first half (vendor prefix equivalent)
            return parts[0] + '.' + '****' + '.' + '****'
        return '****.****.****'
    # Handle colon or hyphen format
    delimiter = ':' if ':' in mac else '-'
    parts = mac.split(delimiter)
    if len(parts) == 6:
        return delimiter.join(parts[:3] + ['**', '**', '**'])
    return '**:**:**:**:**:**'


# Pre-created replacer functions (created once at module level for performance)
def _ipv4_replacer(match):
    """Replacement function for IPv4 addresses."""
    ip = match.group()
    if ip in _NON_SENSITIVE_IPS:
        return ip
    return _mask_ip(ip)


def _ipv6_replacer(match):
    """Replacement function for IPv6 addresses."""
    ip = match.group()
    ip_clean = ip.split('%')[0]  # Remove zone ID for comparison
    if ip_clean in _NON_SENSITIVE_IPS:
        return ip
    return _mask_ip(ip)


def _mac_replacer(match):
    """Replacement function for MAC addresses."""
    mac = match.group()
    return _mask_mac(mac)


def _ssid_replacer(match):
    """Replacement function for SSID fields."""
    prefix = match.group(1)  # e.g., "wl0_ssid": "
    ssid = match.group(2)
    if ssid:
        return prefix + _mask_string(ssid, 3) + '"'
    return match.group(0)


def _wpa_psk_replacer(match):
    """Replacement function for WPA PSK fields - completely redacted."""
    prefix = match.group(1)  # e.g., "wl0_wpa_psk": "
    return prefix + '***REDACTED***"'


def _sensitive_field_replacer(match):
    """Replacement function for generic sensitive JSON fields."""
    prefix = match.group(1)
    value = match.group(2)
    if value:
        return prefix + _mask_string(value, 2) + '"'
    return match.group(0)


def mask_sensitive_data(text: str) -> str:
    """
    Mask sensitive data in text (typically JSON response or request payload).

    Masks:
    - IP addresses (IPv4/IPv6)
    - MAC addresses
    - Serial numbers
    - Hostnames and device names
    - SSID names and WiFi passwords (WPA PSK)
    - Vendor information
    - Authentication tokens and credentials

    Args:
        text: Raw text to mask

    Returns:
        Text with sensitive data masked
    """
    if not text:
        return text

    result = text

    # Mask IP addresses using pre-created replacers (module-level for performance)
    result = _IPV4_PATTERN.sub(_ipv4_replacer, result)
    result = _IPV6_PATTERN.sub(_ipv6_replacer, result)

    # Mask MAC addresses using pre-created replacer
    result = _MAC_PATTERN.sub(_mac_replacer, result)

    # Mask SSID values using pre-created replacer
    result = _SSID_FIELD_PATTERN.sub(_ssid_replacer, result)

    # Mask WiFi passwords (WPA PSK) - completely redact
    result = _WPA_PSK_FIELD_PATTERN.sub(_wpa_psk_replacer, result)

    # Mask other sensitive JSON fields using pre-compiled patterns
    for pattern in _SENSITIVE_FIELD_PATTERNS.values():
        result = pattern.sub(_sensitive_field_replacer, result)

    # Mask login_authorization in form data
    result = _AUTH_PATTERN.sub(r'login_authorization=***REDACTED***', result)

    return result


class SensitiveFormatter(logging.Formatter):
    """
    Logging formatter that masks sensitive information in log messages.

    Automatically masks:
    - IP addresses (IPv4/IPv6)
    - MAC addresses
    - Serial numbers, hostnames, device names
    - SSID names, WiFi passwords, vendor information
    - Authentication tokens and credentials
    """

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        try:
            return mask_sensitive_data(original)
        except Exception:
            # If masking fails, redact entirely to prevent credential leakage
            return "[MASKING FAILED - LOG REDACTED]"
