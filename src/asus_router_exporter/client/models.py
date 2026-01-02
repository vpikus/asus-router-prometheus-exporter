from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum, IntFlag, StrEnum


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
    internet: dict[str, ThroughputInfo]
    wired: ThroughputInfo
    wireless: dict[str, ThroughputInfo]


class WifiBand(IntEnum):
    _2G = 2
    _5G = 1
    _6G = 4
    _60G = 6

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
    WL_6G = 3 #???


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
    hidde_ssid: bool
    mbo_enabled: bool


class DualWanOrigin(StrEnum):
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


class QosType(IntEnum):
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
    qos_type: QosType | None
    bwdpi_app_rulelist: str
    firmver: str
    extendno: str
    territory_code: str
    re_mode: bool
    sw_mode: SwMode
    caps: RouterFeatureCapabilities
    uptime: UptimeInfo
    reboot_schedule: RebootScheduleInfo | None
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


class SwMode(StrEnum):
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


class UsbDeviceType(StrEnum):
    STORAGE = "storage"
    MODEM = "modem"
    PRINTER = "printer"


class WanProtoType(StrEnum):
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


class WanDslProtoType(StrEnum):
    PPPoA = "pppoa"
    IPoA = "ipoa"
    PPPoE = "pppoe"
    IPoE = "ipoe"


class DslTransMode(StrEnum):
    ATM = "atm"
    PTM = "ptm"


class WanStatus(StrEnum):
    STANDBY = "standby"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class WanMode(StrEnum):
    FAIL_OVER = "fo"
    FAIL_BACK = "fb"
    LOAD_BALANCE = "lb"

@dataclass
class WanInfo:
    status: WanStatus
    connection_info: WanConnectionInfo
    active: bool
    ipaddr: str | None = None
    proto: WanProtoType | None = None

@dataclass
class NetworkWanInfo:
    mode: SwMode
    link_internet: LinkInternet
    dual_wan_info: DualWanInfo | None = None
    primary_wan: WanInfo | None = None
    secondary_wan: WanInfo | None = None
    lan_info: LanInfo | None = None

    @property
    def has_internet(self) -> bool:
        return True if self.link_internet == LinkInternet.ONLINE else False


class WanState(IntEnum):
    IDLE = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 4
    DISABLED = 5


class WanSubState(IntEnum):
    OK = 0
    PPP_FAIL = 1
    BAD_CREDENTIALS = 2
    DHCP_FAIL = 3
    IP_CONFLICT = 4


class WanAuxState(IntEnum):
    CONNECTED = 0
    DISCONNECTED = 1


class LinkInternet(IntEnum):
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


class LanState(IntEnum):
    DISCONNECTED = 0
    CONNECTED = 1


class LanProtoType(StrEnum):
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


class PortGroup(StrEnum):
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
    def from_mbps(cls, mbps: int) -> EthernetRate | None:
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
    def from_mbps(cls, mbps: int) -> UsbRate | None:
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
            usb_rate = UsbRate.from_mbps(self.max_supported_speed_rate_mbps)
            return usb_rate.label if usb_rate else "Unknown"
        else:
            eth_rate = EthernetRate.from_mbps(self.max_supported_speed_rate_mbps)
            return eth_rate.label if eth_rate else "Unknown"


class ClientInterface(Enum):
    LAN = (0, "LAN")
    WL_2G = (1, "2.4G")
    WL_5G = (2, "5G")
    WL_5G_2 = (3, "5G")
    WL_6G = (4, "6G")
    WL_6G_2 = (5, "6G")

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def label(self) -> str:
        return self.value[1]

    @classmethod
    def from_code(cls, code: int) -> ClientInterface | None:
        for interface in cls:
            if interface.code == code:
                return interface
        return None


class ClientOperationMode(IntEnum):
    RT = 1
    RE = 2
    AP = 3
    MB = 4


class RssiStrength(IntEnum):
    DANGER = 0
    WEAK = 1
    GOOD = 2
    STRONG = 3
    VERY_STRONG = 4


class ClientIpMethod(StrEnum):
    DHCP = "DHCP"
    STATIC = "Static"
    MANUAL = "Manual"
    OFFLINE = "OffLine"


@dataclass
class TrafficStats:
    rx: int
    tx: int


class ClientInternetMode(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    TIME = "time"


class ClientInternetState(IntEnum):
    ALLOW = 1
    BLOCK = 0


class ClientAmeshRole(StrEnum):
    REPEATER = "re"
    CLIENT = "client"


@dataclass
class ClientAmeshInfo:
    role: ClientAmeshRole | None
    pap_mac: str | None = None
    bind_mac: str | None = None
    bind_band: int | None = None


class ClientBrand(Enum):
    ADOBE = ("ADOBE", 0, 0)
    AMAZON = ("Amazon", 0, 0)
    APPLE = ("Apple", 0, 5)
    ASUS = ("ASUS", 1, 4)
    BELKIN = ("Belkin", 0, 0)
    BIZLINK = ("BizLink", 0, 0)
    BUFFALO = ("BUFFALO", 0, 0)
    DELL = ("Dell", 0, 0)
    DELLKING = ("DellKing", 0, 0)
    D_LINK = ("D-Link", 0, 0)
    FUJITSU_ALT = ("Fujitsu", 0, 0)
    GOOGLE = ("Google", 0, 0)
    HON_HAI_ALT = ("Hon Hai", 0, 0)
    HTC = ("HTC", 0, 0)
    HUAWEI_ALT = ("Huawei", 0, 0)
    IBM = ("IBM", 0, 0)
    LENOVO = ("Lenovo", 0, 0)
    NEC = ("NEC ", 0, 0)
    MICROSOFT = ("Microsoft", 0, 2)
    MSFT = ("Microsoft", 30, 2)
    DHCPCD = ("dhcpcd", 22, 3)
    ANDROID = ("android", 9, 1)
    PANASONIC = ("Panasonic", 0, 0)
    PIONEER = ("PIONEER", 0, 0)
    PIONEER_ALT = ("Pioneer", 0, 0)
    RALINK = ("Ralink", 0, 0)
    SAMSUNG = ("Samsung", 0, 0)
    SONY = ("Sony", 0, 0)
    SYNOLOGY = ("Synology", 0, 0)
    TOSHIBA = ("TOSHIBA", 0, 0)
    TOSHIBA_ALT = ("Toshiba", 0, 0)
    TP_LINK = ("TP-LINK", 0, 0)
    VMWARE = ("VMware", 0, 0)
    AICAM = ("AiCam", 5, 1)
    ZENFONE = ("ZenFone", 28, 1)
    ASUS_PHONE = ("ASUS_Phone", 28, 1)

    @property
    def keyword(self) -> str:
        return self.value[0]

    @property
    def device_type(self) -> int:
        return self.value[1]

    @property
    def os_type(self) -> int:
        return self.value[2]

    @staticmethod
    def find_by_types(device_type: int, os_type: int) -> list[ClientBrand]:
        return [
            b for b in ClientBrand
            if b.device_type == device_type and b.os_type == os_type
        ]


class ClientDeviceCategory(Enum):
    WIRELESS = ("Wireless", 2, 0)
    ROUTER = ("Router", 2, 0)
    VOIP_GATEWAY = ("Voip Gateway", 2, 0)
    NAS = ("NAS", 4, 0)
    IP_NETWORK_CAMERA = ("IP Network Camera", 5, 4)
    MAC_OS = ("Mac OS", 6, 5)
    GAME_CONSOLE = ("Game Console", 7, 0)
    ANDROID_DEVICE = ("Android Device", 9, 1)
    SMARTPHONE = ("Smartphone", 9, 1)
    VOIP_PHONE = ("Voip Phone", 9, 1)
    MIPHONE = ("MiPhone", 9, 1)
    IOS_DEVICE = ("Apple iOS Device", 10, 5)
    IPHONE = ("iPhone", 10, 5)
    APPLE_TV = ("Apple TV", 11, 5)
    MACINTOSH = ("Macintosh", 14, 5)
    PRINTER = ("Printer", 18, 0)
    WINDOWS_PHONE = ("Windows Phone", 19, 2)
    NOKIA = ("Nokia", 19, 0)
    WINDOWS_MOBILE = ("Windows Mobile", 19, 2)
    TABLET = ("Tablet", 20, 1)
    IPAD = ("iPad", 21, 5)
    SMART_TV = ("SmartTV", 23, 0)
    KINDLE = ("Kindle", 25, 0)
    FIRE_TV = ("Fire TV", 25, 0)
    SCANNER = ("Scanner", 26, 0)
    CHROMECAST = ("Chromecast", 27, 0)
    ZENFONE = ("ZenFone", 28, 4)
    PADFONE = ("PadFone", 28, 4)
    ASUS_PAD = ("Asus Pad", 29, 4)
    ASUS_ZENPAD = ("Asus ZenPad", 29, 4)
    TRANSFORMER = ("Transformer", 29, 4)
    DESKTOP_LAPTOP = ("Desktop/Laptop", 34, 0)

    # ---------------------------------------------------------------
    # Properties
    # ---------------------------------------------------------------
    @property
    def keyword(self) -> str:
        return self.value[0]

    @property
    def device_type(self) -> int:
        return self.value[1]

    @property
    def os_type(self) -> int:
        return self.value[2]

    @staticmethod
    def find_by_types(device_type: int, os_type: int) -> list[ClientDeviceCategory]:
        return [
            c for c in ClientDeviceCategory
            if c.device_type == device_type and c.os_type == os_type
        ]


@dataclass
class BaseClientInfo:
    name: str
    nick_name: str
    mac: str
    vendor: str
    online: bool
    os_type: int
    device_type: int
    last_conn_ts: int | None
    last_conn_interface: ClientInterface
    amesh_info: ClientAmeshInfo | None = None

    @property
    def last_conn_datetime(self) -> datetime | None:
        if self.last_conn_ts is None:
            return None
        return datetime.fromtimestamp(self.last_conn_ts)

    @property
    def device_category(self) -> list[ClientDeviceCategory]:
        return ClientDeviceCategory.find_by_types(self.device_type, self.os_type)

    @property
    def device_brand(self) -> list[ClientBrand]:
        return ClientBrand.find_by_types(self.device_type, self.os_type)


@dataclass(kw_only=True)
class ClientInfo(BaseClientInfo):
    """Detailed info about a single client."""
    ipaddr: str
    interface: ClientInterface
    op_mode: ClientOperationMode | None
    rssi: int | None
    ip_method: ClientIpMethod | None
    internet_mode: ClientInternetMode
    internet_state: ClientInternetState
    traffic_stats: TrafficStats | None = None
    throughput_info: ThroughputInfo | None = None
    conn_time: str | None = None

    @property
    def conn_ts(self) -> int | None:
        if self.conn_time is None:
            return None
        h, m, s = map(int, self.conn_time.split(":"))
        return h * 3600 + m * 60 + s

    @property
    def rssi_strength(self) -> RssiStrength | None:
        if self.rssi is None:
            return None

        if self.rssi >= -50:
            result = 4
        elif self.rssi >= -80:
            result = math.ceil((24 + ((self.rssi + 80) * 26) / 10) / 25)
        elif self.rssi >= -90:
            result = math.ceil((((self.rssi + 90) * 26) / 10) / 25)
        else:
            result = 0

        return RssiStrength(result)
