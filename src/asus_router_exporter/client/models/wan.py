"""WAN-related models: WAN info, connection state, dual WAN, DSL, LAN."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from .router import SwMode


class DualWanOrigin(StrEnum):
    NONE = "none"
    WAN = "wan"
    LAN = "lan"
    USB = "usb"
    DSL = "dsl"


class WanMode(StrEnum):
    FAIL_OVER = "fo"
    FAIL_BACK = "fb"
    LOAD_BALANCE = "lb"


@dataclass
class DualWanInfo:
    wan_origins: dict[int, DualWanOrigin]
    wan0_enable: bool
    wan1_enable: bool
    active_wan_unit: int
    enabled: bool
    wans_mode: WanMode


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


class WanState(IntEnum):
    IDLE = 0
    CONNECTING = 1
    CONNECTED = 2
    DISCONNECTED = 3
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
            self.link_internet == LinkInternet.ONLINE
            and self.state == WanState.CONNECTED
            and self.substate == WanSubState.OK
            and self.auxstate == WanAuxState.CONNECTED
        )


@dataclass
class WanInfo:
    status: WanStatus
    connection_info: WanConnectionInfo
    active: bool
    ipaddr: str | None = None
    proto: WanProtoType | None = None


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
        return self.link_internet == LinkInternet.ONLINE
