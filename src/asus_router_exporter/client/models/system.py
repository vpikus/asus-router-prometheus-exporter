"""System-related models: CPU, memory, temperature, uptime, reboot schedule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
