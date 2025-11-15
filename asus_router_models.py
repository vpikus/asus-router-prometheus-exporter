from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo, time
from enum import Enum, IntFlag
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
    smart_connect_enabled: bool
    band_2G_info: Optional[WifiBandInfo] = None
    band_5G_info: Optional[WifiBandInfo] = None
    band_5G_2_info: Optional[WifiBandInfo] = None
    band_6G_info: Optional[WifiBandInfo] = None

    def is_supported(self, b: WifiBand) -> bool:
        return bool(self.bands_count.get(b, 0))

class WifiMode(Enum):
    AUTO = 0
    N_ONLY = 1
    LEGACY = 2
    MIXED = 8
    AX_ONLY = 9

class WifiUnit(Enum):
    WL_2G = 0
    WL_5G = 1
    WL_5G_2 = 2
    WL_6G = 3 #???

class WifiAuthMode(Enum):
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

class WifiCrypto(Enum):
    AES = "aes"
    TKIP_AES = "tkip+aes"

class WifiMfp(Enum):
    """
    Protected Management Frames
    """
    DISABLE = 0
    CAPABLE = 1
    REQUIRED = 2

class WifiWpsWep(Enum):
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
    hidde_ssid: bool
    mbo_enabled: bool

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

class QosType(Enum):
    TRADITIONAL = 0
    ADAPTIVE = 1
    BANDWIDTH_LIMITER = 2
    GEFORCE = 3
    cake = 9

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
    qos_type: Optional[QosType]
    bwdpi_app_rulelist: str
    firmver: str
    extendno: str
    territory_code: str
    re_mode: bool
    sw_mode: SwMode
    caps: RouterFeatureCapabilities
    uptime: UptimeInfo
    reboot_schedule: Optional[RebootScheduleInfo]
    serial_no: str
    software_update_available: bool
    ports_info: list[PortInfo]


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
    active: bool
    ipaddr: Optional[str] = None
    proto: Optional[WanProtoType] = None

@dataclass
class NetworkWanInfo:
    mode: SwMode
    link_internet: LinkInternet
    dual_wan_info: Optional[DualWanInfo] = None
    primary_wan: Optional[WanInfo] = None
    secondary_wan: Optional[WanInfo] = None
    lan_info: Optional[LanInfo] = None

    @property
    def has_internet(self) -> bool:
        return True if self.link_internet == LinkInternet.ONLINE else False

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

class PortCapability(IntFlag):
    WAN = 1 << 0
    LAN = 1 << 1
    GAME = 1 << 2
    PLC = 1 << 3
    WAN2 = 1 << 4
    WAN3 = 1 << 5
    SFPP = 1 << 6
    USB = 1 << 7
    MOBILE = 1 << 8
    WANLAN = 1 << 9
    MOCA = 1 << 10
    WANAUTO = 1 << 12
    IPTV_BRIDGE = 1 << 26
    IPTV_VOIP = 1 << 27
    IPTV_STB = 1 << 28
    DUALWAN_SECONDARY_WAN = 1 << 29
    DUALWAN_PRIMARY_WAN = 1 << 30


class PortGroup(Enum):
    WAN = "W"
    LAN = "L"
    USB = "U"

class EthernetRate(Enum):
    RATE_10 = (10, "10 Mbps")
    RATE_100 = (100, "100 Mbps")
    RATE_1000 = (1000, "1 Gbps")
    RATE_2500 = (2500, "2.5 Gbps")
    RATE_10000 = (10000, "10 Gbps")

    @property
    def mbps(self) -> int:
        return self.value[0]

    @property
    def label(self) -> str:
        return self.value[1]

    @classmethod
    def from_mbps(cls, mbps: int) -> Optional[EthernetRate]:
        for rate in cls:
            if rate.mbps == mbps:
                return rate
        return None


class UsbRate(Enum):
    USB2_0 = (480, "USB2.0")
    USB3_0 = (5000, "USB3.0")
    USB3_2 = (10000, "USB3.2")

    @property
    def mbps(self) -> int:
        return self.value[0]

    @property
    def label(self) -> str:
        return self.value[1]

    @classmethod
    def from_mbps(cls, mbps: int) -> Optional[UsbRate]:
        for rate in cls:
            if rate.mbps == mbps:
                return rate
        return None

@dataclass
class PortInfo:
    """Detailed info about a single port."""
    id: str
    plugged: bool
    capability: PortCapability
    max_supported_speed_rate_mbps: int
    current_speed_rate_mbps: int

    @property
    def group(self) -> PortGroup:
        return PortGroup(self.id[:1])

    @property
    def is_slow_speed(self) -> bool:
        return self.plugged and self.max_supported_speed_rate_mbps > self.current_speed_rate_mbps

    @property
    def special_port_name(self) -> str:
        if self.group == PortGroup.USB:
            return UsbRate.from_mbps(self.max_supported_speed_rate_mbps).label
        else:
            return EthernetRate.from_mbps(self.max_supported_speed_rate_mbps).label
