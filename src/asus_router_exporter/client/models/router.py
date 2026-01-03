"""Router-related models: RouterInfo, capabilities, software mode."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ports import PortInfo
    from .system import RebootScheduleInfo, UptimeInfo


class QosType(IntEnum):
    TRADITIONAL = 0
    ADAPTIVE = 1
    BANDWIDTH_LIMITER = 2
    GEFORCE = 3
    cake = 9


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


class RouterFeatureCapabilities:
    def __init__(self, cap):
        self.caps: dict[str, int] = {str(k): int(v) for k, v in cap.items()}

    def __getitem__(self, key: str) -> int:
        return self.caps.get(key, 0)

    def __contains__(self, key: str) -> bool:
        return key in self.caps

    def is_supported(self, f) -> bool:
        return bool(self.caps.get(f, 0))


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
