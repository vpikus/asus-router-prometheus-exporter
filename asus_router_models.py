from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass
class TemperatureInfo:
    cpu: float

@dataclass
class CpuInfo:
    total: int
    usage: int

@dataclass
class MemoryInfo:
    """Memory statistics from router (all values in kilobytes)."""
    total_kb: int
    """Total memory in kilobytes."""
    used_kb: int
    """Used memory in kilobytes."""
    free_kb: int
    """Free memory in kilobytes."""

@dataclass
class UptimeInfo:
    systime: datetime
    boottime: int

@dataclass
class ThroughputInfo:
    total_upload_bytes: int
    total_download_bytes: int


@dataclass
class NetdevInfo:
    bridge: ThroughputInfo
    internet: dict[int, ThroughputInfo]
    wired: ThroughputInfo
    wireless: dict[int, ThroughputInfo]

class WifiBand(Enum):
    _2G = 2
    _5G = 1
    _6G = 4
    _60G = 6

@dataclass
class WifiInfo:
    bands_count: dict[WifiBand, int]

    def is_supported(self, b: WifiBand) -> bool:
        return bool(self.bands_count.get(b, 0))

class DualWanMode(Enum):
    NONE = 'none'
    WAN = 'wan'
    LAN = 'lan'
    USB = 'usb'
    DSL = 'dsl'

@dataclass
class DualWanInfo:
    modes: dict[int, DualWanMode]
    wan0_enable: bool
    wan1_enable: bool
    active_wan_unit: int
    enabled: bool
    pass


@dataclass
class RouterInfo:
    product_id: str
    lan_hwaddr: str
    lan_hostname: str
    odmpid: str
    hardware_version: str
    bl_version: str
    svc_ready: bool
    qos_enable: bool
    qos_type: int
    bwdpi_app_rulelist: str
    firmver: str
    extendno: str
    territory_code: str
    re_mode: int
    sw_mode: SwMode
    caps: RouterFeatureCapabilities
    uptime: UptimeInfo
    wifi_info: WifiInfo


class RouterFeatureCapabilities:

    def __init__(self, cap):
        self.caps: dict[str, int] = {
            str(k): int(v) for k, v in cap.items()
        }

    def __getitem__(self, key: str) -> int:
        return self.caps.get(key, 0)

    def __contains__(self, key: str) -> bool:
        return key in self.caps

    def is_supported(self, f) -> bool:
        return bool(self.caps.get(f, 0))


class SwMode(Enum):
    RE = "re"
    """
    Repeater
    """
    AP = "ap"
    """
    Access Point
    """
    MB = "MB"
    """
    MediaBridge
    """
    EW2 = "ew2"
    """
    Express Way 2G
    """
    EW5 = "ew5"
    """
    Express Way 5G
    """
    HS = "hs"
    """
    Hotspot
    """
    RT = "rt"
    """
    Router
    """

class UsbDeviceType(Enum):
    STORAGE = "storage"
    MODEM = "modem"
    PRINTER = "printer"

