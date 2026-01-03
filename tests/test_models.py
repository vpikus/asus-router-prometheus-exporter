"""
Tests for asus_router_models module.
"""

from datetime import datetime

import pytest

from asus_router_exporter.client.models import (
    BaseClientInfo,
    ClientInfo,
    ClientInterface,
    ClientInternetMode,
    ClientInternetState,
    ClientIpMethod,
    ClientOperationMode,
    CpuInfo,
    DualWanOrigin,
    EthernetRate,
    LinkInternet,
    MemoryInfo,
    NetdevInfo,
    PortCapability,
    PortGroup,
    PortInfo,
    RebootScheduleConf,
    RouterFeatureCapabilities,
    RssiStrength,
    SwMode,
    TemperatureInfo,
    ThroughputInfo,
    UptimeInfo,
    WanAuxState,
    WanConnectionInfo,
    WanMode,
    WanState,
    WanStatus,
    WanSubState,
    WifiAuthMode,
    WifiBand,
    WifiBandInfo,
    WifiCrypto,
    WifiInfo,
    WifiMfp,
    WifiMode,
    WifiWpsWep,
)


class TestTemperatureInfo:
    """Tests for TemperatureInfo dataclass."""

    def test_temperature_info_creation(self):
        temp = TemperatureInfo(cpu=52.759)
        assert temp.cpu == 52.759


class TestCpuInfo:
    """Tests for CpuInfo dataclass."""

    def test_cpu_info_creation(self):
        cpu = CpuInfo(total=3367570, usage=141252)
        assert cpu.total == 3367570
        assert cpu.usage == 141252


class TestMemoryInfo:
    """Tests for MemoryInfo dataclass."""

    def test_memory_info_creation(self):
        mem = MemoryInfo(total_kb=1048576, used_kb=499540, free_kb=549036)
        assert mem.total_kb == 1048576
        assert mem.used_kb == 499540
        assert mem.free_kb == 549036


class TestThroughputInfo:
    """Tests for ThroughputInfo dataclass."""

    def test_throughput_info_creation(self):
        tp = ThroughputInfo(total_upload_bytes=1000, total_download_bytes=2000)
        assert tp.total_upload_bytes == 1000
        assert tp.total_download_bytes == 2000


class TestNetdevInfo:
    """Tests for NetdevInfo dataclass."""

    def test_netdev_info_creation(self):
        bridge = ThroughputInfo(100, 200)
        wired = ThroughputInfo(300, 400)
        internet = {0: ThroughputInfo(500, 600)}
        wireless = {0: ThroughputInfo(700, 800)}

        netdev = NetdevInfo(bridge=bridge, wired=wired, internet=internet, wireless=wireless)

        assert netdev.bridge.total_upload_bytes == 100
        assert netdev.wired.total_download_bytes == 400
        assert len(netdev.internet) == 1
        assert len(netdev.wireless) == 1


class TestWifiBand:
    """Tests for WifiBand enum."""

    def test_wifi_band_values(self):
        assert WifiBand._2G.value == 2
        assert WifiBand._5G.value == 1
        assert WifiBand._6G.value == 4


class TestWifiMode:
    """Tests for WifiMode enum."""

    def test_wifi_mode_values(self):
        assert WifiMode.AUTO.value == 0
        assert WifiMode.N_ONLY.value == 1
        assert WifiMode.LEGACY.value == 2
        assert WifiMode.AX_ONLY.value == 9


class TestWifiAuthMode:
    """Tests for WifiAuthMode enum."""

    def test_wifi_auth_mode_values(self):
        assert WifiAuthMode.OPEN == "open"
        assert WifiAuthMode.PSK2 == "psk2"
        assert WifiAuthMode.SAE == "sae"


class TestWifiBandInfo:
    """Tests for WifiBandInfo dataclass."""

    def test_wifi_band_info_creation(self):
        band = WifiBandInfo(
            ssid="MyNetwork",
            mac="04:42:1A:0F:9E:D0",
            mode=WifiMode.AUTO,
            auth_mode=WifiAuthMode.PSK2,
            crypto=WifiCrypto.AES,
            mfp=WifiMfp.DISABLE,
            wep=WifiWpsWep.NONE,
            hidden_ssid=False,
            mbo_enabled=False,
        )
        assert band.ssid == "MyNetwork"
        assert band.auth_mode == WifiAuthMode.PSK2


class TestSwMode:
    """Tests for SwMode enum."""

    def test_sw_mode_values(self):
        assert SwMode.RT == "rt"
        assert SwMode.AP == "ap"
        assert SwMode.RE == "re"
        assert SwMode.MB == "MB"


class TestWanConnectionInfo:
    """Tests for WanConnectionInfo dataclass."""

    def test_wan_connection_info_connected(self):
        info = WanConnectionInfo(
            state=WanState.CONNECTED,
            substate=WanSubState.OK,
            auxstate=WanAuxState.CONNECTED,
            link_internet=LinkInternet.ONLINE,
        )
        assert info.is_connected is True

    def test_wan_connection_info_disconnected(self):
        info = WanConnectionInfo(
            state=WanState.IDLE,
            substate=WanSubState.OK,
            auxstate=WanAuxState.DISCONNECTED,
            link_internet=LinkInternet.OFFLINE,
        )
        assert info.is_connected is False


class TestPortInfo:
    """Tests for PortInfo dataclass."""

    def test_port_info_creation(self):
        port = PortInfo(
            id="L1",
            plugged=True,
            capability=PortCapability.LAN,
            max_supported_speed_rate_mbps=1000,
            current_speed_rate_mbps=100,
        )
        assert port.id == "L1"
        assert port.plugged is True
        assert port.group == PortGroup.LAN

    def test_port_info_is_slow_speed(self):
        port = PortInfo(
            id="L1",
            plugged=True,
            capability=PortCapability.LAN,
            max_supported_speed_rate_mbps=1000,
            current_speed_rate_mbps=100,
        )
        assert port.is_slow_speed is True

    def test_port_info_not_slow_when_unplugged(self):
        port = PortInfo(
            id="L1",
            plugged=False,
            capability=PortCapability.LAN,
            max_supported_speed_rate_mbps=1000,
            current_speed_rate_mbps=0,
        )
        assert port.is_slow_speed is False

    def test_port_group_wan(self):
        port = PortInfo(
            id="W0",
            plugged=True,
            capability=PortCapability.WAN,
            max_supported_speed_rate_mbps=1000,
            current_speed_rate_mbps=1000,
        )
        assert port.group == PortGroup.WAN


class TestEthernetRate:
    """Tests for EthernetRate enum."""

    def test_ethernet_rate_from_mbps(self):
        assert EthernetRate.from_mbps(1000) == EthernetRate.RATE_1000
        assert EthernetRate.from_mbps(100) == EthernetRate.RATE_100
        assert EthernetRate.from_mbps(10) == EthernetRate.RATE_10

    def test_ethernet_rate_properties(self):
        rate = EthernetRate.RATE_1000
        assert rate.mbps == 1000
        assert rate.label == "1 Gbps"


class TestClientInterface:
    """Tests for ClientInterface enum."""

    def test_client_interface_from_code(self):
        assert ClientInterface.from_code(0) == ClientInterface.LAN
        assert ClientInterface.from_code(1) == ClientInterface.WL_2G
        assert ClientInterface.from_code(2) == ClientInterface.WL_5G

    def test_client_interface_properties(self):
        iface = ClientInterface.WL_2G
        assert iface.code == 1
        assert iface.label == "2.4G"


class TestClientInfo:
    """Tests for ClientInfo dataclass."""

    def test_client_info_conn_ts(self):
        client = ClientInfo(
            name="TestDevice",
            nick_name="My Phone",
            mac="AA:BB:CC:DD:EE:FF",
            vendor="Apple",
            online=True,
            os_type=5,
            device_type=10,
            last_conn_ts=1735730100,
            last_conn_interface=ClientInterface.WL_5G,
            ipaddr="192.168.1.100",
            interface=ClientInterface.WL_5G,
            op_mode=None,
            rssi=-55,
            ip_method=ClientIpMethod.DHCP,
            internet_mode=ClientInternetMode.ALLOW,
            internet_state=ClientInternetState.ALLOW,
            conn_time="01:30:45",
        )
        # 1*3600 + 30*60 + 45 = 5445
        assert client.conn_ts == 5445

    def test_client_info_rssi_strength_strong(self):
        client = ClientInfo(
            name="Test",
            nick_name="",
            mac="AA:BB:CC:DD:EE:FF",
            vendor="",
            online=True,
            os_type=0,
            device_type=0,
            last_conn_ts=None,
            last_conn_interface=ClientInterface.WL_5G,
            ipaddr="192.168.1.100",
            interface=ClientInterface.WL_5G,
            op_mode=None,
            rssi=-45,
            ip_method=None,
            internet_mode=ClientInternetMode.ALLOW,
            internet_state=ClientInternetState.ALLOW,
        )
        assert client.rssi_strength == RssiStrength.VERY_STRONG

    def test_client_info_rssi_strength_weak(self):
        client = ClientInfo(
            name="Test",
            nick_name="",
            mac="AA:BB:CC:DD:EE:FF",
            vendor="",
            online=True,
            os_type=0,
            device_type=0,
            last_conn_ts=None,
            last_conn_interface=ClientInterface.WL_5G,
            ipaddr="192.168.1.100",
            interface=ClientInterface.WL_5G,
            op_mode=None,
            rssi=-85,
            ip_method=None,
            internet_mode=ClientInternetMode.ALLOW,
            internet_state=ClientInternetState.ALLOW,
        )
        assert client.rssi_strength == RssiStrength.WEAK


class TestRebootScheduleConf:
    """Tests for RebootScheduleConf dataclass."""

    def test_reboot_schedule_weekday_enabled(self):
        # "1000100" binary = 68 decimal, means Sunday and Thursday enabled
        conf = RebootScheduleConf(weekday_mask=68, hh=4, mm=0)
        # Monday (Python weekday 0) -> ASUS index 1, bit 5 from right
        assert conf.is_weekday_enabled(0) is False  # Monday
        # Thursday (Python weekday 3) -> ASUS index 4, bit 2 from right
        assert conf.is_weekday_enabled(3) is True  # Thursday

    def test_reboot_schedule_set_time(self):
        conf = RebootScheduleConf(weekday_mask=0, hh=4, mm=30)
        dt = datetime(2026, 1, 1, 12, 0, 0)
        result = conf.set_time(dt)
        assert result.hour == 4
        assert result.minute == 30
        assert result.second == 0


class TestRouterFeatureCapabilities:
    """Tests for RouterFeatureCapabilities class."""

    def test_capabilities_is_supported(self):
        caps = RouterFeatureCapabilities({"dualwan": 1, "5G": 1, "stainfo": 0})
        assert caps.is_supported("dualwan") is True
        assert caps.is_supported("5G") is True
        assert caps.is_supported("stainfo") is False
        assert caps.is_supported("unknown") is False

    def test_capabilities_getitem(self):
        caps = RouterFeatureCapabilities({"dualwan": 1})
        assert caps["dualwan"] == 1
        assert caps["unknown"] == 0

    def test_capabilities_contains(self):
        caps = RouterFeatureCapabilities({"dualwan": 1})
        assert "dualwan" in caps
        assert "unknown" not in caps
