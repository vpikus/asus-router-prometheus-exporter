"""
Tests for asus_router_utils module.
"""

import pytest

from asus_router_exporter.utils.parsing import (
    ids_for,
    int_or_none,
    is_valid_mac,
    parse_hex,
    safe_int,
    to_bool,
    trim_to_none,
)


class TestIsValidMac:
    """Tests for is_valid_mac function."""

    def test_valid_mac_uppercase(self):
        assert is_valid_mac("AA:BB:CC:DD:EE:FF") is True

    def test_valid_mac_lowercase(self):
        assert is_valid_mac("aa:bb:cc:dd:ee:ff") is True

    def test_valid_mac_mixed_case(self):
        assert is_valid_mac("Aa:Bb:Cc:Dd:Ee:Ff") is True

    def test_valid_mac_with_zeros(self):
        assert is_valid_mac("00:00:00:00:00:00") is True

    def test_invalid_mac_wrong_delimiter(self):
        assert is_valid_mac("AA-BB-CC-DD-EE-FF") is False

    def test_invalid_mac_too_short(self):
        assert is_valid_mac("AA:BB:CC:DD:EE") is False

    def test_invalid_mac_too_long(self):
        assert is_valid_mac("AA:BB:CC:DD:EE:FF:00") is False

    def test_invalid_mac_invalid_chars(self):
        assert is_valid_mac("GG:HH:II:JJ:KK:LL") is False

    def test_invalid_mac_empty(self):
        assert is_valid_mac("") is False

    def test_invalid_mac_no_colons(self):
        assert is_valid_mac("AABBCCDDEEFF") is False


class TestParseHex:
    """Tests for parse_hex function."""

    def test_parse_hex_with_prefix(self):
        assert parse_hex("0x78023dfa") == 0x78023dfa

    def test_parse_hex_without_prefix(self):
        assert parse_hex("ff") == 255

    def test_parse_hex_zero(self):
        assert parse_hex("0x0") == 0

    def test_parse_hex_large_number(self):
        assert parse_hex("0x1e2a5ad36") == 0x1e2a5ad36

    def test_parse_hex_uppercase(self):
        assert parse_hex("0xABCDEF") == 11259375


class TestIdsFor:
    """Tests for ids_for function."""

    def test_ids_for_internet(self):
        keys = ["INTERNET_rx", "INTERNET_tx", "INTERNET1_rx", "INTERNET1_tx"]
        result = ids_for("INTERNET", keys)
        assert result == ["", "1"]

    def test_ids_for_wireless(self):
        keys = ["WIRELESS0_rx", "WIRELESS0_tx", "WIRELESS1_rx", "WIRELESS1_tx"]
        result = ids_for("WIRELESS", keys)
        assert result == ["0", "1"]

    def test_ids_for_cpu(self):
        keys = ["cpu1_total", "cpu1_usage", "cpu2_total", "cpu2_usage", "cpu3_total", "cpu3_usage"]
        result = ids_for("cpu", keys)
        assert result == ["1", "2", "3"]

    def test_ids_for_no_match(self):
        keys = ["other_key", "another_key"]
        result = ids_for("INTERNET", keys)
        assert result == []

    def test_ids_for_empty_keys(self):
        result = ids_for("PREFIX", [])
        assert result == []

    def test_ids_for_mixed_keys(self):
        keys = ["BRIDGE_rx", "INTERNET_tx", "WIRELESS0_rx", "OTHER"]
        result = ids_for("BRIDGE", keys)
        assert result == [""]


class TestSafeInt:
    """Tests for safe_int function."""

    def test_safe_int_valid_string(self):
        assert safe_int("123") == 123

    def test_safe_int_valid_int(self):
        assert safe_int(456) == 456

    def test_safe_int_invalid_string(self):
        assert safe_int("abc") == 0

    def test_safe_int_empty_string(self):
        assert safe_int("") == 0

    def test_safe_int_none(self):
        assert safe_int(None) == 0

    def test_safe_int_negative(self):
        assert safe_int("-100") == -100

    def test_safe_int_float_string(self):
        assert safe_int("3.14") == 0


class TestIntOrNone:
    """Tests for int_or_none function."""

    def test_int_or_none_valid(self):
        assert int_or_none("123") == 123

    def test_int_or_none_zero(self):
        assert int_or_none("0") == 0

    def test_int_or_none_empty(self):
        assert int_or_none("") is None

    def test_int_or_none_none(self):
        assert int_or_none(None) is None

    def test_int_or_none_whitespace(self):
        assert int_or_none("   ") is None

    def test_int_or_none_with_whitespace(self):
        assert int_or_none("  42  ") == 42


class TestTrimToNone:
    """Tests for trim_to_none function."""

    def test_trim_to_none_normal_string(self):
        assert trim_to_none("hello") == "hello"

    def test_trim_to_none_with_whitespace(self):
        assert trim_to_none("  hello  ") == "hello"

    def test_trim_to_none_empty(self):
        assert trim_to_none("") is None

    def test_trim_to_none_whitespace_only(self):
        assert trim_to_none("   ") is None

    def test_trim_to_none_none(self):
        assert trim_to_none(None) is None

    def test_trim_to_none_number(self):
        assert trim_to_none(123) == "123"


class TestToBool:
    """Tests for to_bool function."""

    def test_to_bool_one(self):
        assert to_bool("1") is True

    def test_to_bool_zero(self):
        assert to_bool("0") is False

    def test_to_bool_other_number(self):
        assert to_bool("5") is True

    def test_to_bool_negative(self):
        assert to_bool("-1") is True
