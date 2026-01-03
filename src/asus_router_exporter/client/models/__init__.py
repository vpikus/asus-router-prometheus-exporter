"""
Data models for the ASUS Router client.

Organized by domain:
- system: CPU, memory, temperature, uptime, reboot
- network: throughput, netdev, traffic
- wireless: WiFi bands, modes, authentication
- wan: WAN connection, dual WAN, DSL, LAN
- ports: Ethernet ports, USB ports
- clients: connected clients, device info
- router: RouterInfo, capabilities, software mode
"""

from .clients import (
    BaseClientInfo,
    ClientAmeshInfo,
    ClientAmeshRole,
    ClientBrand,
    ClientDeviceCategory,
    ClientInfo,
    ClientInterface,
    ClientInternetMode,
    ClientInternetState,
    ClientIpMethod,
    ClientOperationMode,
    RssiStrength,
)
from .network import (
    NetdevInfo,
    ThroughputInfo,
    TrafficStats,
)
from .ports import (
    EthernetRate,
    PortCapability,
    PortGroup,
    PortInfo,
    UsbDeviceType,
    UsbRate,
)
from .router import (
    QosType,
    RouterFeatureCapabilities,
    RouterInfo,
    SwMode,
)
from .system import (
    CpuInfo,
    MemoryInfo,
    RebootScheduleConf,
    RebootScheduleInfo,
    TemperatureInfo,
    UptimeInfo,
)
from .wan import (
    DslInfo,
    DslTransMode,
    DualWanInfo,
    DualWanOrigin,
    LanInfo,
    LanProtoType,
    LanState,
    LinkInternet,
    NetworkWanInfo,
    WanAuxState,
    WanConnectionInfo,
    WanDslProtoType,
    WanInfo,
    WanMode,
    WanProtoType,
    WanState,
    WanStatus,
    WanSubState,
)
from .wireless import (
    WifiAuthMode,
    WifiBand,
    WifiBandInfo,
    WifiCrypto,
    WifiInfo,
    WifiMfp,
    WifiMode,
    WifiUnit,
    WifiWpsWep,
)

__all__ = [
    # System
    "TemperatureInfo",
    "CpuInfo",
    "MemoryInfo",
    "UptimeInfo",
    "RebootScheduleConf",
    "RebootScheduleInfo",
    # Network
    "ThroughputInfo",
    "NetdevInfo",
    "TrafficStats",
    # Wireless
    "WifiBand",
    "WifiInfo",
    "WifiMode",
    "WifiUnit",
    "WifiAuthMode",
    "WifiCrypto",
    "WifiMfp",
    "WifiWpsWep",
    "WifiBandInfo",
    # WAN
    "DualWanOrigin",
    "DualWanInfo",
    "WanProtoType",
    "WanDslProtoType",
    "DslTransMode",
    "WanStatus",
    "WanMode",
    "WanInfo",
    "NetworkWanInfo",
    "WanState",
    "WanSubState",
    "WanAuxState",
    "LinkInternet",
    "WanConnectionInfo",
    "DslInfo",
    "LanState",
    "LanProtoType",
    "LanInfo",
    # Ports
    "UsbDeviceType",
    "PortCapability",
    "PortGroup",
    "EthernetRate",
    "UsbRate",
    "PortInfo",
    # Clients
    "ClientInterface",
    "ClientOperationMode",
    "RssiStrength",
    "ClientIpMethod",
    "ClientInternetMode",
    "ClientInternetState",
    "ClientAmeshRole",
    "ClientAmeshInfo",
    "ClientBrand",
    "ClientDeviceCategory",
    "BaseClientInfo",
    "ClientInfo",
    # Router
    "QosType",
    "RouterInfo",
    "RouterFeatureCapabilities",
    "SwMode",
]
