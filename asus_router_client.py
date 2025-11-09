from __future__ import annotations

import base64
import json
import re
from collections import Counter
from datetime import timedelta

import requests

from asus_router_client_exceptions import *
from asus_router_models import *
from asus_router_utils import *

ASUS_CLIENT_DEFAULT_HEADERS = {
    "User-Agent": "asusrouter-Android-DUTUtil-1.0.0.245"
}

DEFAULT_TIMEOUT = 10


@dataclass
class RouterClient:
    host: str
    session: requests.Session

    @staticmethod
    def __handle_response(response: requests.Response) -> str:
        response.raise_for_status()
        try:
            data = response.json()
            if "error_status" in data:
                # TODO: handle 2 (probable token expired), 10 (captcha is required) and other statuses
                raise AuthenticationException()
        except json.decoder.JSONDecodeError:
            pass
        return response.text

    def __get_hook(self, name: str, args: str = "") -> str:
        response = self.session.get(f"{self.host}/appGet.cgi",
                                    params={
                                        "hook": f"{name}({args})"
                                    },
                                    headers=ASUS_CLIENT_DEFAULT_HEADERS,
                                    timeout=DEFAULT_TIMEOUT)
        return self.__handle_response(response)

    def __get_nvram(self, *nvrams: str):
        def __nvramget(*vars_: str) -> str:
            return ";".join(f"nvram_get({v})" for v in vars_)

        response = self.session.get(f"{self.host}/appGet.cgi",
                                    params={
                                        "hook": f"{__nvramget(*nvrams)})"
                                    },
                                    headers=ASUS_CLIENT_DEFAULT_HEADERS,
                                    timeout=DEFAULT_TIMEOUT)

        text = self.__handle_response(response)
        return json.loads(text)

    def get_core_temp(self) -> TemperatureInfo:
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

    def get_uptime(self) -> UptimeInfo:
        response = self.__get_hook("uptime")
        data = json.loads(response)
        uptime_raw = data["uptime"].split("(")
        systime = datetime.strptime(uptime_raw[0].strip(), "%a, %d %b %Y %H:%M:%S %z")
        boottime = int(uptime_raw[1].split(" ")[0])
        return UptimeInfo(systime=systime, boottime=boottime)

    @staticmethod
    def _parse_schedule(schedule: str) -> RebootScheduleConf:
        mask = int(schedule[:7], 2)
        hh = int(schedule[7:9])
        mm = int(schedule[9:11])
        return RebootScheduleConf(
            weekday_mask=mask,
            hh=hh,
            mm=mm
        )

    def get_reboot_schedule_time(self) -> Optional[RebootScheduleInfo]:
        caps = self.get_supported_features()
        if not caps.is_supported("reboot_schedule"):
            return None
        nvrams = self.__get_nvram("reboot_schedule_enable", "reboot_schedule")
        if not to_bool(nvrams.get("reboot_schedule_enable", "0")):
            return None
        reboot_schedule = self._parse_schedule(nvrams["reboot_schedule"])
        uptime = self.get_uptime()
        systime = uptime.systime
        for delta in range(8):
            day_dt = systime + timedelta(days=delta)
            if reboot_schedule.is_weekday_enabled(day_dt.weekday()):
                candidate = reboot_schedule.set_time(day_dt)
                if delta > 0 or candidate >= systime:
                    until_ms = max(0, int((candidate - systime).total_seconds() * 1000))
                    return RebootScheduleInfo(
                        next_at=candidate,
                        until_ms=until_ms,
                        schedule=reboot_schedule
                    )
        return None

    def get_cpu_usage(self) -> list[CpuInfo]:
        response = self.__get_hook("cpu_usage")
        data = json.loads("{" + response[14:])
        cpu_infos: list[CpuInfo] = []

        cpu_ids = ids_for("cpu", data.keys())

        for cid in cpu_ids:
            prefix = f"cpu{cid}"

            cpu_infos.append(CpuInfo(
                usage=int(data[f"{prefix}_usage"]),
                total=int(data[f"{prefix}_total"])
            ))

        return cpu_infos

    def get_memory_usage(self) -> MemoryInfo:
        response = self.__get_hook("memory_usage")
        data = json.loads("{" + response[17:])
        return MemoryInfo(
            total_kb=int(data["mem_total"]),
            used_kb=int(data["mem_used"]),
            free_kb=int(data["mem_free"])
        )

    def get_wl_nband_info(self) -> dict[WifiBand, int]:
        response = self.__get_hook("wl_nband_info")
        wl_nband_info = json.loads(response)["wl_nband_info"]
        wl_nband_array = [int(v) for v in wl_nband_info]
        counts = Counter(wl_nband_array)

        return {
            band: counts.get(band.value, 0)
            for band in WifiBand
        }

    def get_plugged_usb_devices(self) -> list[UsbDeviceType]:
        response = self.__get_hook("show_usb_path")
        all_usb_statuses = json.loads(response)["show_usb_path"]
        usb_devices = []
        for usb_status in all_usb_statuses:
            usb_devices.append(UsbDeviceType(usb_status))
        return usb_devices

    def get_wireless_band_info(self, wl_unit: WifiUnit, repeater:bool) -> WifiBandInfo:
        unit = f"{wl_unit.value}{'.1' if repeater else ''}"
        nvrams = self.__get_nvram(f"wl{unit}_mbo_enable", f"wl{unit}_ssid", f"wl{unit}_nmode_x",
                                  f"wl{unit}_auth_mode_x", f"wl{unit}_crypto", f"wl{unit}_mfp",
                                  f"wl{unit}_wep_x", f"wl{unit}_closed", f"wl{unit}_hwaddr")
        return WifiBandInfo(
            ssid=nvrams[f"wl{unit}_ssid"],
            mac=nvrams[f"wl{unit}_hwaddr"],
            mode=WifiMode(int(nvrams[f"wl{unit}_nmode_x"])),
            auth_mode=WifiAuthMode(nvrams[f"wl{unit}_auth_mode_x"]),
            crypto=WifiCrypto(nvrams[f"wl{unit}_crypto"]),
            mfp=WifiMfp(int(nvrams[f"wl{unit}_mfp"])),
            wep=WifiWpsWep(int(nvrams[f"wl{unit}_wep_x"])),
            hidde_ssid=to_bool(nvrams[f"wl{unit}_closed"]),
            mbo_enabled=to_bool(nvrams.get(f"wl{unit}_mbo_enable", "0"))
        )


    def get_wireless_info(self) -> WifiInfo:
        wl_nband_info = self.get_wl_nband_info()
        nvrams = self.__get_nvram("wps_enable", "wlc_band", "smart_connect_x")
        wifi_info = WifiInfo(
            bands_count=wl_nband_info,
            wps_enabled=to_bool(nvrams.get("wps_enable", "0")),
            smart_connect_enabled=to_bool(nvrams.get("smart_connect_enable", "0")),
        )

        caps = self.get_supported_features()
        sw_mode = self.get_sw_mode()
        wlc_band = nvrams[f"wlc_band"]
        concurrep_support = caps.is_supported("concurrep")
        if caps.is_supported("2.4G"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_2G))
            wifi_info.band_2G_info = self.get_wireless_band_info(WifiUnit.WL_2G, repeater)
        if caps.is_supported("5G"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_5G))
            wifi_info.band_5G_info = self.get_wireless_band_info(WifiUnit.WL_5G, repeater)
        if caps.is_supported("5G-2"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_5G_2))
            wifi_info.band_5G_2_info = self.get_wireless_band_info(WifiUnit.WL_5G_2, repeater)
        if caps.is_supported("wifi6e"):
            repeater = sw_mode == SwMode.RE and (concurrep_support or wlc_band == str(WifiUnit.WL_6G))
            wifi_info.band_6G_info = self.get_wireless_band_info(WifiUnit.WL_6G, repeater)

        return wifi_info

    def get_info(self) -> RouterInfo:
        nvrams = self.__get_nvram("productid", "lan_hwaddr", "lan_hostname", "odmpid", "hardware_version",
                                  "bl_version", "svc_ready", "qos_enable", "bwdpi_app_rulelist", "qos_type", "firmver",
                                  "extendno", "territory_code", "re_mode", "serial_no")

        sw_mode = self.get_sw_mode()
        caps = self.get_supported_features()
        uptime = self.get_uptime()
        reboot_schedule = self.get_reboot_schedule_time()

        return RouterInfo(
            product_id=nvrams["productid"],
            lan_hwaddr=nvrams["lan_hwaddr"],
            lan_hostname=nvrams["lan_hostname"],
            odmpid=nvrams["odmpid"],
            hardware_version=nvrams["hardware_version"],
            bl_version=nvrams["bl_version"],
            sw_mode=sw_mode,
            svc_ready=to_bool(nvrams.get("svc_ready", "0")),
            qos_enable=to_bool(nvrams.get("qos_enable", "0")),
            bwdpi_app_rulelist=nvrams["bwdpi_app_rulelist"].replace("&#60", "<"),
            qos_type=QosType(int(nvrams["qos_type"])) if nvrams["qos_type"] != "" else None,
            firmver=nvrams["firmver"],
            extendno=nvrams["extendno"],
            territory_code=nvrams["territory_code"],
            re_mode=to_bool(nvrams["re_mode"]),
            caps=caps,
            uptime=uptime,
            serial_no=nvrams["serial_no"],
            reboot_schedule=reboot_schedule
        )

    def get_netdev(self) -> NetdevInfo:
        response = self.__get_hook("netdev", "appobj")
        data = json.loads(response)
        netdev = data["netdev"]

        bridge = ThroughputInfo(
            total_upload_bytes=parse_hex(netdev["BRIDGE_tx"]),
            total_download_bytes=parse_hex(netdev["BRIDGE_rx"])
        )

        wired = ThroughputInfo(
            total_upload_bytes=parse_hex(netdev["WIRED_tx"]),
            total_download_bytes=parse_hex(netdev["WIRED_rx"])
        )

        internet_ids = ids_for("INTERNET", netdev.keys())
        internet: dict[int, ThroughputInfo] = {
            iid: ThroughputInfo(
                total_upload_bytes=parse_hex(netdev.get(f"INTERNET{iid}_tx")),
                total_download_bytes=parse_hex(netdev.get(f"INTERNET{iid}_rx")),
            )
            for iid in internet_ids
        }

        wireless_ids = ids_for("WIRELESS", netdev.keys())
        wireless: dict[int, ThroughputInfo] = {
            wid: ThroughputInfo(
                total_upload_bytes=parse_hex(netdev.get(f"WIRELESS{wid}_tx")),
                total_download_bytes=parse_hex(netdev.get(f"WIRELESS{wid}_rx")),
            )
            for wid in wireless_ids
        }

        return NetdevInfo(bridge=bridge, internet=internet, wired=wired, wireless=wireless)

    def get_supported_features(self) -> RouterFeatureCapabilities:
        response = self.__get_hook("get_ui_support")
        data = json.loads(response)
        cap = RouterFeatureCapabilities(data["get_ui_support"])
        return cap

    def get_sw_mode(self) -> SwMode:
        nvrams = self.__get_nvram("sw_mode", "wlc_psta", "wlc_express")
        sw_mode = int(nvrams["sw_mode"])
        wlc_psta = safe_int(nvrams.get("wlc_psta", 0))
        wlc_express = safe_int(nvrams.get("wlc_express", 0))

        mode = SwMode.RT
        if ((sw_mode == 2 and wlc_psta == 0) or (sw_mode == 3 and wlc_psta == 2)) and wlc_express == 0:
            # Repeater
            mode = SwMode.RE
        elif sw_mode == 3 and (wlc_psta == 0 or wlc_psta == ""):
            # Access Point
            mode = SwMode.AP
        elif (
                (sw_mode == 3 and wlc_psta in (1, 3) and wlc_express == 0)
                or (sw_mode == 2 and wlc_psta == 1 and wlc_express == 0)
        ):
            # Media Bridge
            mode = SwMode.MB
        elif sw_mode == 2 and wlc_psta == 0 and wlc_express == 1:
            # ExpressWay 2G
            mode = SwMode.EW2
        elif sw_mode == 2 and wlc_psta == 0 and wlc_express == 2:
            # ExpressWay 5G
            mode = SwMode.EW5
        elif sw_mode == 5:
            # Hotspot
            mode = SwMode.HS

        return mode

    def get_dual_wan_info(self) -> DualWanInfo:
        nvrams = self.__get_nvram("wans_dualwan", "wan0_enable", "wan1_enable", "wans_mode")
        active_wan_unit = int(json.loads(self.__get_hook("get_wan_unit"))["get_wan_unit"])
        caps = self.get_supported_features()

        wans_dualwan_raw = nvrams["wans_dualwan"].split()
        wans_dualwan: dict[int, DualWanOrigin] = {
            i: DualWanOrigin(part.lower()) if part.lower() in DualWanOrigin._value2member_map_ else DualWanOrigin.NONE
            for i, part in enumerate(wans_dualwan_raw)
        }

        dualwan_enabled = caps.is_supported("dualwan") and DualWanOrigin.NONE not in set(wans_dualwan.values())
        return DualWanInfo(
            wan_origins=wans_dualwan,
            wan0_enable=to_bool(nvrams.get("wan0_enable", "0")),
            wan1_enable=to_bool(nvrams.get("wan1_enable", "0")),
            active_wan_unit=active_wan_unit,
            enabled=dualwan_enabled,
            wans_mode=WanMode(nvrams["wans_mode"])
        )

    def get_wan_connection_info(self, wan_index: int = 0) -> WanConnectionInfo:
        nvrams = self.__get_nvram(f"wan{wan_index}_state_t", f"wan{wan_index}_sbstate_t",
                                  f"wan{wan_index}_auxstate_t", "link_internet")
        return WanConnectionInfo(
            state=WanState(int(nvrams[f"wan{wan_index}_state_t"])),
            substate=WanSubState(int(nvrams[f"wan{wan_index}_sbstate_t"])),
            auxstate=WanAuxState(int(nvrams[f"wan{wan_index}_auxstate_t"])),
            link_internet=LinkInternet(int(nvrams["link_internet"]))
        )

    def get_dsl_info(self) -> DslInfo:
        nvrams = self.__get_nvram("dsl0_proto", "dslx_transmode")
        return DslInfo(
            proto=WanDslProtoType(nvrams["dsl0_proto"]),
            transmode=DslTransMode(nvrams["dslx_transmode"]),
        )

    def get_wan_info(self, wan_index: int = 0) -> WanInfo:
        dual_wan_info = self.get_dual_wan_info()
        wan_connection_info = self.get_wan_connection_info(wan_index)
        status = WanStatus.CONNECTED if wan_connection_info.is_connected else WanStatus.DISCONNECTED
        if (dual_wan_info.enabled
                and dual_wan_info.active_wan_unit != wan_index
                and dual_wan_info.wans_mode in [WanMode.FAIL_BACK, WanMode.FAIL_OVER]):
            status = WanStatus.STANDBY
        wan_info = WanInfo(status=status,
                           connection_info=wan_connection_info,
                           active=dual_wan_info.active_wan_unit == wan_index)
        caps = self.get_supported_features()
        if status == WanStatus.CONNECTED:
            nvrams = self.__get_nvram(f"wan{wan_index}_ipaddr", f"wan{wan_index}_proto")
            wan_info.ipaddr = nvrams[f"wan{wan_index}_ipaddr"]
            wan_info.proto = WanProtoType(nvrams[f"wan{wan_index}_proto"])
            wan_origin = dual_wan_info.wan_origins[wan_index]
            if caps.is_supported("usbX") and wan_origin == DualWanOrigin.USB:
                wan_info.proto = WanProtoType.USB
            elif caps.is_supported("dsl") and wan_origin == DualWanOrigin.DSL:
                dsl_info = self.get_dsl_info()
                if (dsl_info.transmode == DslTransMode.ATM
                        and dsl_info.proto in [WanDslProtoType.IPoA, WanDslProtoType.PPPoA]):
                    wan_info.proto = WanProtoType(dsl_info.proto.value)
        return wan_info

    def get_network_wan_info(self) -> NetworkWanInfo:
        sw_mode = self.get_sw_mode()
        nvrams = self.__get_nvram("link_internet")
        network_wan_info = NetworkWanInfo(
            mode=sw_mode,
            link_internet=LinkInternet(int(nvrams["link_internet"])),
        )
        if sw_mode == SwMode.RT:
            network_wan_info.primary_wan = self.get_wan_info(0)
            dual_wan_info = self.get_dual_wan_info()
            network_wan_info.dual_wan_info = dual_wan_info
            if dual_wan_info.enabled:
                network_wan_info.secondary_wan = self.get_wan_info(1)
        elif sw_mode == SwMode.AP:
            nvrams = self.__get_nvram("lan_ipaddr", "lan_proto")
            network_wan_info.lan_info = LanInfo(
                state=LanState.CONNECTED,
                ipaddr=nvrams["lan_ipaddr"],
                proto=LanProtoType(nvrams["lan_proto"]),
            )
        return network_wan_info


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
