"""
Metric collectors for the ASUS Router Exporter.

Each collector is responsible for a specific category of metrics.
"""

from .base import BaseCollector, LabeledMetricsMixin
from .clients import ClientsCollector
from .cpu import CPUCollector
from .memory import MemoryCollector
from .netdev import NetdevCollector
from .ports import PortsCollector
from .router_info import RouterInfoCollector
from .wan import WANCollector
from .wireless import WirelessCollector

__all__ = [
    "BaseCollector",
    "LabeledMetricsMixin",
    "ClientsCollector",
    "CPUCollector",
    "MemoryCollector",
    "NetdevCollector",
    "PortsCollector",
    "RouterInfoCollector",
    "WANCollector",
    "WirelessCollector",
]

# All collectors that should be registered by default
DEFAULT_COLLECTORS = [
    RouterInfoCollector,
    CPUCollector,
    MemoryCollector,
    NetdevCollector,
    WANCollector,
    WirelessCollector,
    PortsCollector,
    ClientsCollector,
]
