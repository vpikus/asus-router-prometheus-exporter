"""Network-related models: throughput, netdev, traffic stats."""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass
class TrafficStats:
    rx: int
    tx: int
