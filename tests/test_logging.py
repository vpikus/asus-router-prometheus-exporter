"""
Tests for asus_router_logging module.
"""

import logging
from unittest.mock import patch

import pytest

from asus_router_exporter.utils.logging import (
    SensitiveFormatter,
    _mask_ip,
    _mask_mac,
    _mask_string,
    mask_sensitive_data,
)


class TestMaskString:
    """Tests for _mask_string function."""

    def test_mask_string_normal(self):
        assert _mask_string("HelloWorld", 2) == "He********"

    def test_mask_string_short(self):
        assert _mask_string("Hi", 2) == "**"

    def test_mask_string_very_short(self):
        assert _mask_string("A", 2) == "*"

    def test_mask_string_empty(self):
        assert _mask_string("", 2) == ""

    def test_mask_string_custom_visible(self):
        assert _mask_string("TestString", 4) == "Test******"


class TestMaskIp:
    """Tests for _mask_ip function."""

    def test_mask_ipv4(self):
        assert _mask_ip("192.168.1.100") == "192.*.*.*"

    def test_mask_ipv4_public(self):
        assert _mask_ip("203.0.113.50") == "203.*.*.*"

    def test_mask_ipv6(self):
        assert _mask_ip("fe80:0000:0000:0000:1234:5678:90ab:cdef") == "fe80:****:****:****"

    def test_mask_ipv4_mapped_ipv6(self):
        assert _mask_ip("::ffff:192.168.1.1") == "::****:*.*.*"

    def test_mask_ipv4_compatible_ipv6(self):
        assert _mask_ip("::192.168.1.1") == "::****:*.*.*"

    def test_mask_ipv6_with_zone_id(self):
        # Zone ID should be stripped before masking
        assert _mask_ip("fe80::1%eth0") == "fe80:****:****:****"


class TestMaskSensitiveDataIpv6ZoneId:
    """Tests for IPv6 addresses with zone IDs."""

    def test_mask_ipv6_zone_id_in_text(self):
        text = "Link-local address: fe80::1234:5678%wlan0"
        result = mask_sensitive_data(text)
        assert "fe80::1234:5678%wlan0" not in result
        assert "fe80:****" in result

    def test_mask_ipv6_compressed_with_zone(self):
        text = "Address: fe80::1%eth0"
        result = mask_sensitive_data(text)
        assert "fe80::1%eth0" not in result


class TestMaskMac:
    """Tests for _mask_mac function."""

    def test_mask_mac_colon_delimiter(self):
        assert _mask_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:**:**:**"

    def test_mask_mac_hyphen_delimiter(self):
        assert _mask_mac("AA-BB-CC-DD-EE-FF") == "AA-BB-CC-**-**-**"

    def test_mask_mac_lowercase(self):
        assert _mask_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:**:**:**"

    def test_mask_mac_invalid_format(self):
        assert _mask_mac("invalid") == "**:**:**:**:**:**"

    def test_mask_mac_cisco_format(self):
        assert _mask_mac("0011.2233.4455") == "0011.****.****"


class TestMaskSensitiveData:
    """Tests for mask_sensitive_data function."""

    def test_mask_ipv4_addresses(self):
        text = "Client connected from 192.168.1.100"
        result = mask_sensitive_data(text)
        assert "192.168.1.100" not in result
        assert "192.*.*.*" in result

    def test_mask_mac_addresses(self):
        text = '{"mac": "AA:BB:CC:DD:EE:FF"}'
        result = mask_sensitive_data(text)
        assert "DD:EE:FF" not in result
        assert "AA:BB:CC:**:**:**" in result

    def test_mask_serial_number(self):
        text = '{"serial_no": "ABC123456789"}'
        result = mask_sensitive_data(text)
        assert "ABC123456789" not in result
        assert "AB**********" in result

    def test_mask_hostname(self):
        text = '{"lan_hostname": "MyRouter"}'
        result = mask_sensitive_data(text)
        assert "MyRouter" not in result

    def test_mask_ssid(self):
        text = '{"wl0_ssid": "MyHomeNetwork"}'
        result = mask_sensitive_data(text)
        assert "MyHomeNetwork" not in result
        assert "MyH**********" in result

    def test_mask_ssid_5g(self):
        text = '{"wl1_ssid": "MyNetwork_5G"}'
        result = mask_sensitive_data(text)
        assert "MyNetwork_5G" not in result

    def test_mask_client_name(self):
        text = '{"name": "Johns-iPhone"}'
        result = mask_sensitive_data(text)
        assert "Johns-iPhone" not in result

    def test_mask_nickname(self):
        text = '{"nickName": "John Phone"}'
        result = mask_sensitive_data(text)
        assert "John Phone" not in result

    def test_mask_vendor(self):
        text = '{"vendor": "Apple Inc."}'
        result = mask_sensitive_data(text)
        assert "Apple Inc." not in result

    def test_mask_login_authorization(self):
        text = "login_authorization=YWRtaW46cGFzc3dvcmQ="
        result = mask_sensitive_data(text)
        assert "YWRtaW46cGFzc3dvcmQ=" not in result
        assert "***REDACTED***" in result

    def test_mask_login_authorization_url_encoded(self):
        # URL-encoded token with %2B (+) and %3D (=)
        text = "login_authorization=YWRtaW46cGFzc3dvcmQ%3D"
        result = mask_sensitive_data(text)
        assert "YWRtaW46cGFzc3dvcmQ%3D" not in result
        assert "***REDACTED***" in result

    def test_mask_ipv4_mapped_ipv6_address(self):
        text = "Address: ::ffff:192.168.1.100"
        result = mask_sensitive_data(text)
        assert "192.168.1.100" not in result

    def test_mask_ssid_with_subunit(self):
        # Test wl0.1_ssid pattern (guest network)
        text = '{"wl0.1_ssid": "GuestNetwork"}'
        result = mask_sensitive_data(text)
        assert "GuestNetwork" not in result
        assert "Gue*********" in result  # 12 chars, 3 visible = 9 asterisks

    def test_preserve_non_sensitive_localhost(self):
        text = "Connecting to 127.0.0.1"
        result = mask_sensitive_data(text)
        assert "127.0.0.1" in result

    def test_preserve_non_sensitive_broadcast(self):
        text = "Broadcast address: 255.255.255.255"
        result = mask_sensitive_data(text)
        assert "255.255.255.255" in result

    def test_preserve_non_sensitive_zero(self):
        text = "Default: 0.0.0.0"
        result = mask_sensitive_data(text)
        assert "0.0.0.0" in result

    def test_empty_string(self):
        assert mask_sensitive_data("") == ""

    def test_none_input(self):
        assert mask_sensitive_data(None) is None

    def test_complex_json(self):
        text = """{
            "productid": "RT-AX88U",
            "lan_hwaddr": "AA:BB:CC:DD:EE:FF",
            "lan_hostname": "MyRouter",
            "serial_no": "ABC123456789",
            "wl0_ssid": "HomeNetwork",
            "clients": {
                "11:22:33:44:55:66": {
                    "name": "iPhone",
                    "ip": "192.168.1.100",
                    "vendor": "Apple"
                }
            }
        }"""
        result = mask_sensitive_data(text)

        # Product ID should be preserved
        assert "RT-AX88U" in result

        # Sensitive data should be masked
        assert "DD:EE:FF" not in result
        assert "MyRouter" not in result
        assert "ABC123456789" not in result
        assert "HomeNetwork" not in result
        assert "192.168.1.100" not in result
        assert "44:55:66" not in result

    def test_mask_wpa_psk(self):
        text = '{"wl0_wpa_psk": "MySecretPassword123"}'
        result = mask_sensitive_data(text)
        assert "MySecretPassword123" not in result
        assert "***REDACTED***" in result

    def test_mask_wpa_psk_subunit(self):
        # Guest network PSK
        text = '{"wl0.1_wpa_psk": "GuestPassword"}'
        result = mask_sensitive_data(text)
        assert "GuestPassword" not in result
        assert "***REDACTED***" in result

    def test_mask_http_passwd(self):
        text = '{"http_passwd": "admin_password"}'
        result = mask_sensitive_data(text)
        assert "admin_password" not in result
        assert "ad***********" in result

    def test_mask_pppoe_credentials(self):
        text = '{"wan_pppoe_passwd": "MyPPPoEPassword", "wan_pppoe_username": "user@isp.com"}'
        result = mask_sensitive_data(text)
        assert "MyPPPoEPassword" not in result
        assert "user@isp.com" not in result

    def test_mask_ddns_credentials(self):
        text = '{"ddns_passwd": "ddns_secret", "ddns_username": "myuser123"}'
        result = mask_sensitive_data(text)
        assert "ddns_secret" not in result
        assert "myuser123" not in result

    def test_mask_vpn_password(self):
        text = '{"vpn_server_password": "VpnSecret123"}'
        result = mask_sensitive_data(text)
        assert "VpnSecret123" not in result

    def test_mask_cisco_mac_in_text(self):
        text = "Device MAC: 0011.2233.4455"
        result = mask_sensitive_data(text)
        assert "0011.2233.4455" not in result
        assert "0011.****.****" in result

    def test_mask_escaped_quotes_in_name(self):
        # Test handling of escaped quotes in JSON values
        text = '{"name": "John\\"Doe"}'
        result = mask_sensitive_data(text)
        assert 'John\\"Doe' not in result

    def test_mask_asus_token(self):
        text = '{"asus_token": "abc123def456"}'
        result = mask_sensitive_data(text)
        assert "abc123def456" not in result
        assert "ab**********" in result


class TestSensitiveFormatter:
    """Tests for SensitiveFormatter class."""

    def test_formatter_masks_ip(self):
        formatter = SensitiveFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Connected to 192.168.1.1",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "192.168.1.1" not in result
        assert "192.*.*.*" in result

    def test_formatter_masks_mac(self):
        formatter = SensitiveFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="MAC: AA:BB:CC:DD:EE:FF",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "DD:EE:FF" not in result
        assert "AA:BB:CC:**:**:**" in result

    def test_formatter_masks_auth_token(self):
        formatter = SensitiveFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Auth: login_authorization=abc123def456",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "abc123def456" not in result
        assert "***REDACTED***" in result

    def test_formatter_with_format_string(self):
        formatter = SensitiveFormatter("%(levelname)s - %(message)s")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="IP: 10.0.0.1", args=(), exc_info=None
        )
        result = formatter.format(record)
        assert result.startswith("INFO - ")
        assert "10.0.0.1" not in result
        assert "10.*.*.*" in result

    def test_formatter_preserves_normal_messages(self):
        formatter = SensitiveFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Normal log message without sensitive data",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result == "Normal log message without sensitive data"

    def test_formatter_handles_masking_exception(self):
        """Test that formatter returns redacted message if masking fails."""
        formatter = SensitiveFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Sensitive data: 192.168.1.1",
            args=(),
            exc_info=None,
        )
        # Mock mask_sensitive_data to raise an exception
        with patch("asus_router_exporter.utils.logging.mask_sensitive_data", side_effect=Exception("Regex error")):
            result = formatter.format(record)
            assert result == "[MASKING FAILED - LOG REDACTED]"
