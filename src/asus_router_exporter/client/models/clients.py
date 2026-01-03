"""Client-related models: connected clients, device brands, categories."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum, StrEnum

from .network import ThroughputInfo, TrafficStats


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
        return [b for b in ClientBrand if b.device_type == device_type and b.os_type == os_type]


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
        return [c for c in ClientDeviceCategory if c.device_type == device_type and c.os_type == os_type]


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
