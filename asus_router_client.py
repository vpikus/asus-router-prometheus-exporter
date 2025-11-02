from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime

import requests

import asus_router_utils

ASUS_CLIENT_DEFAULT_HEADERS = {
    "User-Agent": "asusrouter-Android-DUTUtil-1.0.0.245"
}

DEFAULT_TIMEOUT = 10

@dataclass
class TemperatureInfo:
    cpu: float

@dataclass
class CpuInfo:
    total: int
    usage: int

@dataclass
class MemoryInfo:
    total: int
    used: int
    free: int

@dataclass
class UptimeInfo:
    uptime: datetime
    uptime_sec: int

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


@dataclass
class RouterClient:
    host: str
    session: requests.Session

    def __execute_hook(self, *hooks: str) -> str:
        response = self.session.get(f"{self.host}/appGet.cgi",
                                    params={
                                        "hook": ";".join(hooks),
                                    },
                                    headers=ASUS_CLIENT_DEFAULT_HEADERS,
                                    timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.text

    def core_temp(self) -> TemperatureInfo:
        response = self.session.get(f"{self.host}/ajax_coretmp.asp",
                                    headers=ASUS_CLIENT_DEFAULT_HEADERS,
                                    timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        payload = response.text
        pattern = re.compile(r'(\w+)\s*=\s*("?[^";]+"?);')
        parsed = dict((m.group(1), m.group(2).strip('"')) for m in pattern.finditer(payload))

        return TemperatureInfo(
            cpu=float(parsed["curr_cpuTemp"])
        )

    def uptime(self) -> UptimeInfo:
        response = self.__execute_hook("uptime()")
        data = json.loads(response)
        uptime_raw = data["uptime"].split("(")
        uptime = datetime.strptime(uptime_raw[0].strip(), "%a, %d %b %Y %H:%M:%S %z")
        uptime_sec = int(uptime_raw[1].split(" ")[0])
        return UptimeInfo(uptime=uptime, uptime_sec=uptime_sec)

    def cpu_usage(self) -> list[CpuInfo]:
        response = self.__execute_hook("cpu_usage()")
        data = json.loads("{" + response[14:])
        cpu_infos: list[CpuInfo] = []

        cpu_ids = asus_router_utils.ids_for("cpu", data.keys())

        for cid in cpu_ids:
            prefix = f"cpu{cid}"

            cpu_infos.append(CpuInfo(
                usage=int(data[f"{prefix}_usage"]),
                total=int(data[f"{prefix}_total"])
            ))

        return cpu_infos

    def memory_usage(self) -> MemoryInfo:
        response = self.__execute_hook("memory_usage()")
        data = json.loads("{" + response[17:])
        return MemoryInfo(
            total=int(data["mem_total"]),
            used=int(data["mem_used"]),
            free=int(data["mem_free"])
        )

    def productid(self) -> str:
        response = self.__execute_hook("nvram_get(productid)")
        data = json.loads(response)
        return data["productid"]

    def netdev(self) -> NetdevInfo:
        response = self.__execute_hook("netdev(appobj)")
        data = json.loads(response)
        netdev = data["netdev"]

        bridge = ThroughputInfo(
            total_upload_bytes=asus_router_utils.parse_hex(netdev["BRIDGE_tx"]),
            total_download_bytes=asus_router_utils.parse_hex(netdev["BRIDGE_rx"])
        )

        wired = ThroughputInfo(
            total_upload_bytes=asus_router_utils.parse_hex(netdev["WIRED_tx"]),
            total_download_bytes=asus_router_utils.parse_hex(netdev["WIRED_rx"])
        )

        internet_ids = asus_router_utils.ids_for("INTERNET", netdev.keys())
        internet: dict[int, ThroughputInfo] = {
            iid: ThroughputInfo(
                total_upload_bytes=asus_router_utils.parse_hex(netdev.get(f"INTERNET{iid}_tx")),
                total_download_bytes=asus_router_utils.parse_hex(netdev.get(f"INTERNET{iid}_rx")),
            )
            for iid in internet_ids
        }

        wireless_ids = asus_router_utils.ids_for("WIRELESS", netdev.keys())
        wireless: dict[int, ThroughputInfo] = {
            wid: ThroughputInfo(
                total_upload_bytes=asus_router_utils.parse_hex(netdev.get(f"WIRELESS{wid}_tx")),
                total_download_bytes=asus_router_utils.parse_hex(netdev.get(f"WIRELESS{wid}_rx")),
            )
            for wid in wireless_ids
        }

        return NetdevInfo(bridge=bridge, internet=internet, wired=wired, wireless=wireless)

    def wanlink(self) -> str:
        response = self.__execute_hook("wanlink()")
        print(response)

class RouterClientFactory:

    def __init__(self, host):
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"

        self.host = host.rstrip("/")

    def auth(self, auth) -> RouterClient:
        token = base64.b64encode(auth.encode("utf-8")).decode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = f"login_authorization={token}"
        session = requests.Session()
        response = session.post(f"{self.host}/login.cgi",
                                headers={**ASUS_CLIENT_DEFAULT_HEADERS, **headers},
                                data=payload,
                                timeout=DEFAULT_TIMEOUT)

        response.raise_for_status()
        return RouterClient(self.host, session)
