"""Wireless-related models: WiFi bands, modes, authentication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class WifiBand(IntEnum):
    _2G = 2
    _5G = 1
    _6G = 4
    _60G = 6


class WifiMode(IntEnum):
    AUTO = 0
    N_ONLY = 1
    LEGACY = 2
    MIXED = 8
    AX_ONLY = 9


class WifiUnit(IntEnum):
    WL_2G = 0
    WL_5G = 1
    WL_5G_2 = 2
    WL_6G = 3  # ???


class WifiAuthMode(StrEnum):
    OPEN = "open"
    SHARED = "shared"
    PSK = "psk"
    PSK2 = "psk2"
    SAE = "sae"
    PSKPSK2 = "pskpsk2"
    PSK2SAE = "psk2sae"
    WPA = "wpa"
    WPA2 = "wpa2"
    WPAWPA2 = "wpawpa2"
    RADIUS = "radius"


class WifiCrypto(StrEnum):
    AES = "aes"
    TKIP_AES = "tkip+aes"


class WifiMfp(IntEnum):
    """
    Protected Management Frames
    """

    DISABLE = 0
    CAPABLE = 1
    REQUIRED = 2


class WifiWpsWep(IntEnum):
    """
    Wired Equivalent Privacy
    """

    NONE = 0
    WEP_64b = 1
    WEP_128b = 2


@dataclass
class WifiBandInfo:
    ssid: str
    mac: str
    mode: WifiMode
    auth_mode: WifiAuthMode
    crypto: WifiCrypto
    mfp: WifiMfp
    wep: WifiWpsWep
    hidden_ssid: bool
    mbo_enabled: bool


@dataclass
class WifiInfo:
    bands_count: dict[WifiBand, int]
    wps_enabled: bool
    smart_connect_enabled: bool
    band_2G_info: WifiBandInfo | None = None
    band_5G_info: WifiBandInfo | None = None
    band_5G_2_info: WifiBandInfo | None = None
    band_6G_info: WifiBandInfo | None = None

    def is_supported(self, b: WifiBand) -> bool:
        return bool(self.bands_count.get(b, 0))
