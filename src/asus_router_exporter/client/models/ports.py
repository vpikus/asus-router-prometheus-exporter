"""Port-related models: Ethernet ports, USB ports, capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntFlag, StrEnum


class UsbDeviceType(StrEnum):
    STORAGE = "storage"
    MODEM = "modem"
    PRINTER = "printer"


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
