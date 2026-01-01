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

_IPV6_PATTERN = re.compile(
    r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|'
    r'\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b|'
    r'\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b|'
    r'\b::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}\b'
)

_MAC_PATTERN = re.compile(
    r'\b(?:[0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}\b'
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
]

# SSID pattern (wl*_ssid fields)
_SSID_FIELD_PATTERN = re.compile(r'"wl[0-9.]*_ssid"\s*:\s*"([^"]*)"')

# Login authorization in form data
_AUTH_PATTERN = re.compile(r'login_authorization=([A-Za-z0-9+/=]+)')


def _mask_string(value: str, visible_chars: int = 2) -> str:
    """Mask a string, keeping only first few characters visible."""
    if len(value) <= visible_chars:
        return '*' * len(value)
    return value[:visible_chars] + '*' * (len(value) - visible_chars)


def _mask_ip(ip: str) -> str:
    """Mask an IP address, keeping only first octet/segment visible."""
    if '.' in ip:
        # IPv4: show first octet
        parts = ip.split('.')
        return parts[0] + '.*.*.*'
    else:
        # IPv6: show first segment
        parts = ip.split(':')
        return parts[0] + ':****:****:****'


def _mask_mac(mac: str) -> str:
    """Mask a MAC address, keeping vendor prefix (first 3 octets) visible."""
    delimiter = ':' if ':' in mac else '-'
    parts = mac.split(delimiter)
    if len(parts) == 6:
        return delimiter.join(parts[:3] + ['**', '**', '**'])
    return '**:**:**:**:**:**'


def mask_sensitive_data(text: str) -> str:
    """
    Mask sensitive data in text (typically JSON response or request payload).

    Masks:
    - IP addresses (IPv4/IPv6)
    - MAC addresses
    - Serial numbers
    - Hostnames and device names
    - SSID names
    - Vendor information
    - Authentication tokens

    Args:
        text: Raw text to mask

    Returns:
        Text with sensitive data masked
    """
    if not text:
        return text

    result = text

    # Mask IP addresses
    for match in _IPV4_PATTERN.finditer(result):
        ip = match.group()
        # Skip common non-sensitive IPs
        if ip not in ('0.0.0.0', '255.255.255.255', '127.0.0.1'):
            result = result.replace(ip, _mask_ip(ip))

    for match in _IPV6_PATTERN.finditer(result):
        ip = match.group()
        if ip not in ('::', '::1'):
            result = result.replace(ip, _mask_ip(ip))

    # Mask MAC addresses
    for match in _MAC_PATTERN.finditer(result):
        mac = match.group()
        result = result.replace(mac, _mask_mac(mac))

    # Mask SSID values
    for match in _SSID_FIELD_PATTERN.finditer(result):
        original_ssid = match.group(1)
        if original_ssid:
            masked_ssid = _mask_string(original_ssid, 3)
            result = result.replace(f'"{original_ssid}"', f'"{masked_ssid}"')

    # Mask other sensitive JSON fields
    for field in _SENSITIVE_FIELDS:
        pattern = re.compile(rf'"{field}"\s*:\s*"([^"]*)"')
        for match in pattern.finditer(result):
            original_value = match.group(1)
            if original_value:
                masked_value = _mask_string(original_value, 2)
                result = result.replace(
                    f'"{field}":"{original_value}"',
                    f'"{field}":"{masked_value}"'
                )
                result = result.replace(
                    f'"{field}": "{original_value}"',
                    f'"{field}": "{masked_value}"'
                )

    # Mask login_authorization in form data
    for match in _AUTH_PATTERN.finditer(result):
        token = match.group(1)
        result = result.replace(f'login_authorization={token}', 'login_authorization=***REDACTED***')

    return result


class SensitiveFormatter(logging.Formatter):
    """
    Logging formatter that masks sensitive information in log messages.

    Automatically masks:
    - IP addresses (IPv4/IPv6)
    - MAC addresses
    - Serial numbers, hostnames, device names
    - SSID names, vendor information
    - Authentication tokens
    """

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return mask_sensitive_data(original)
