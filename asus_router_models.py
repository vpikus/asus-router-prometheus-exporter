from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo, time
from enum import Enum
from typing import Optional


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
class RebootScheduleConf:
    weekday_mask: int
    """
    Bit-mask for weekday reboot, 0=Sunday, 1=Monday, 2=Tuesday, etc.
    """
    hh: int
    mm: int

    def is_weekday_enabled(self, weekday: int) -> bool:
        weekday_index_asus = (weekday + 1) % 7
        return ((self.weekday_mask >> (6 - weekday_index_asus)) & 1) == 1

    def set_time(self, dt: datetime) -> datetime:
        return dt.replace(hour=self.hh, minute=self.mm, second=0, microsecond=0)


@dataclass
class RebootScheduleInfo:
    next_at: datetime
    until_ms: int
    schedule: RebootScheduleConf

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
    wps_enabled: bool

    def is_supported(self, b: WifiBand) -> bool:
        return bool(self.bands_count.get(b, 0))

class DualWanOrigin(Enum):
    NONE = 'none'
    WAN = 'wan'
    LAN = 'lan'
    USB = 'usb'
    DSL = 'dsl'

@dataclass
class DualWanInfo:
    wan_origins: dict[int, DualWanOrigin]
    wan0_enable: bool
    wan1_enable: bool
    active_wan_unit: int
    enabled: bool
    wans_mode: WanMode
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
    reboot_schedule: Optional[RebootScheduleInfo]
    serial_no: str


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

class WanProtoType(Enum):
    DHCP = "dhcp"
    STATIC = "static"
    L2TP = "l2tp"
    PPTP = "pptp"
    Lw4o6 = "lw4o6"
    MAP_E = "map-e"
    V6PLUS = "v6plus"
    PPPoA = "pppoa"
    IPoA = "ipoa"
    PPPoE = "pppoe"
    IPoE = "ipoe"
    OCNVC = "ocnvc"
    DSLITE = "dslite"
    V6OPT = "v6opt"
    USB = "usb"

class WanDslProtoType(Enum):
    PPPoA = "pppoa"
    IPoA = "ipoa"
    PPPoE = "pppoe"
    IPoE = "ipoe"

class DslTransMode(Enum):
    ATM = "atm"
    PTM = "ptm"


class WanStatus(Enum):
    STANDBY = "standby"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

class WanMode(Enum):
    FAIL_OVER = "fo"
    FAIL_BACK = "fb"
    LOAD_BALANCE = "lb"

@dataclass
class WanInfo:
    status: WanStatus
    connection_info: WanConnectionInfo
    ipaddr: Optional[str] = None
    proto: Optional[WanProtoType] = None

@dataclass
class NetworkWanInfo:
    mode: SwMode
    dual_wan_info: Optional[DualWanInfo] = None
    primary_wan: Optional[WanInfo] = None
    secondary_wan: Optional[WanInfo] = None
    lan_info: Optional[LanInfo] = None

class WanState(Enum):
    IDLE = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 4
    DISABLED = 5

class WanSubState(Enum):
    OK = 0
    PPP_FAIL = 1
    BAD_CREDENTIALS = 2
    DHCP_FAIL = 3
    IP_CONFLICT = 4

class WanAuxState(Enum):
    CONNECTED = 0
    DISCONNECTED = 1

class LinkInternet(Enum):
    OFFLINE = 0
    TESTING = 1
    ONLINE = 2


@dataclass
class WanConnectionInfo:
    state: WanState
    substate: WanSubState
    auxstate: WanAuxState
    link_internet: LinkInternet

    @property
    def is_connected(self) -> bool:
        return (
            self.link_internet == LinkInternet.ONLINE and
            self.state == WanState.CONNECTED and
            self.substate == WanSubState.OK and
            self.auxstate == WanAuxState.CONNECTED
        )

@dataclass
class DslInfo:
    transmode: DslTransMode
    proto: WanDslProtoType

class LanState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1

class LanProtoType(Enum):
    DHCP = "dhcp"
    STATIC = "static"
    PPPoE = "pppoe"
    L2TP = "l2tp"
    PPTP = "pptp"

@dataclass
class LanInfo:
    state: LanState
    ipaddr: str
    proto: LanProtoType