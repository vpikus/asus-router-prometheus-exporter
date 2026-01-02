"""
Tests for asus_router_client module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from asus_router_exporter.client import RouterClient, RouterClientFactory
from asus_router_exporter.core.exceptions import AuthenticationError
from asus_router_exporter.client.models import (
    SwMode,
    WifiBand,
    WanState,
    WanSubState,
    WanAuxState,
    LinkInternet,
    WanMode,
    DualWanOrigin,
    PortCapability,
)

from tests.fixtures import (
    MEMORY_USAGE_RESPONSE,
    CPU_USAGE_RESPONSE,
    NETDEV_RESPONSE,
    UPTIME_RESPONSE,
    CORE_TEMP_RESPONSE,
    WL_NBAND_INFO_RESPONSE,
    GET_WAN_UNIT_RESPONSE,
    SW_MODE_NVRAM_RESPONSE,
    DUAL_WAN_NVRAM_RESPONSE,
    WAN_STATE_NVRAM_RESPONSE,
    LINK_INTERNET_NVRAM_RESPONSE,
    PORT_STATUS_RESPONSE,
    UI_SUPPORT_RESPONSE,
    GET_CLIENTLIST_RESPONSE,
    GET_CLIENTLIST_DB_RESPONSE,
    SHOW_USB_PATH_RESPONSE,
    LOGIN_SUCCESS_RESPONSE,
    LOGIN_ERROR_RESPONSE,
)


def create_mock_response(text, status_code=200):
    """Create a mock response object."""
    response = Mock(spec=requests.Response)
    response.text = text
    response.status_code = status_code
    response.url = "http://192.168.1.1/appGet.cgi"
    response.raise_for_status = Mock()

    def json_side_effect():
        import json
        return json.loads(text)

    response.json = json_side_effect
    return response


def create_client_with_mock_session():
    """Create a RouterClient with a mocked session."""
    session = Mock(spec=requests.Session)
    return RouterClient(host="http://192.168.1.1", session=session), session


class TestRouterClientFactory:
    """Tests for RouterClientFactory class."""

    def test_factory_adds_http_prefix(self):
        factory = RouterClientFactory("192.168.1.1")
        assert factory.host == "http://192.168.1.1"

    def test_factory_keeps_existing_http(self):
        factory = RouterClientFactory("http://192.168.1.1")
        assert factory.host == "http://192.168.1.1"

    def test_factory_keeps_existing_https(self):
        factory = RouterClientFactory("https://192.168.1.1")
        assert factory.host == "https://192.168.1.1"

    def test_factory_strips_trailing_slash(self):
        factory = RouterClientFactory("http://192.168.1.1/")
        assert factory.host == "http://192.168.1.1"

    @patch('asus_router_exporter.client.router_client.requests.Session')
    def test_factory_auth_success(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        mock_response = create_mock_response(LOGIN_SUCCESS_RESPONSE)
        mock_session.post.return_value = mock_response

        factory = RouterClientFactory("192.168.1.1")
        client = factory.auth("admin:password")

        assert isinstance(client, RouterClient)
        mock_session.post.assert_called_once()


class TestRouterClientGetCoreTemp:
    """Tests for get_core_temp method."""

    def test_get_core_temp(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(CORE_TEMP_RESPONSE)

        temp = client.get_core_temp()

        assert temp.cpu == 52.759
        session.get.assert_called_once()


class TestRouterClientGetUptime:
    """Tests for get_uptime method."""

    def test_get_uptime(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(UPTIME_RESPONSE)

        uptime = client.get_uptime()

        assert uptime.boottime == 33962
        assert uptime.systime.year == 2026
        assert uptime.systime.month == 1
        assert uptime.systime.day == 1


class TestRouterClientGetCpuUsage:
    """Tests for get_cpu_usage method."""

    def test_get_cpu_usage(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(CPU_USAGE_RESPONSE)

        cpu_list = client.get_cpu_usage()

        assert len(cpu_list) == 4
        assert cpu_list[0].total == 3367570
        assert cpu_list[0].usage == 141252
        assert cpu_list[1].total == 3377595
        assert cpu_list[1].usage == 72288


class TestRouterClientGetMemoryUsage:
    """Tests for get_memory_usage method."""

    def test_get_memory_usage(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(MEMORY_USAGE_RESPONSE)

        mem = client.get_memory_usage()

        assert mem.total_kb == 1048576
        assert mem.used_kb == 499540
        assert mem.free_kb == 549036


class TestRouterClientGetNetdev:
    """Tests for get_netdev method."""

    def test_get_netdev(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(NETDEV_RESPONSE)

        netdev = client.get_netdev()

        assert netdev.bridge.total_download_bytes == 0x78023dfa
        assert netdev.bridge.total_upload_bytes == 0x1e2a5ad36
        assert netdev.wired.total_download_bytes == 0x1efd44512
        assert "" in netdev.internet  # INTERNET_rx/tx
        assert "1" in netdev.internet  # INTERNET1_rx/tx
        assert "0" in netdev.wireless  # WIRELESS0_rx/tx
        assert "1" in netdev.wireless  # WIRELESS1_rx/tx


class TestRouterClientGetWlNbandInfo:
    """Tests for get_wl_nband_info method."""

    def test_get_wl_nband_info(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(WL_NBAND_INFO_RESPONSE)

        bands = client.get_wl_nband_info()

        assert bands[WifiBand._2G] == 1
        assert bands[WifiBand._5G] == 1


class TestRouterClientGetSwMode:
    """Tests for get_sw_mode method."""

    def test_get_sw_mode_router(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(SW_MODE_NVRAM_RESPONSE)

        mode = client.get_sw_mode()

        assert mode == SwMode.RT


class TestRouterClientGetDualWanInfo:
    """Tests for get_dual_wan_info method."""

    def test_get_dual_wan_info(self):
        client, session = create_client_with_mock_session()

        # Need multiple responses for the multiple API calls
        responses = [
            create_mock_response(DUAL_WAN_NVRAM_RESPONSE),
            create_mock_response(GET_WAN_UNIT_RESPONSE),
            create_mock_response(UI_SUPPORT_RESPONSE),
        ]
        session.get.side_effect = responses

        dual_wan = client.get_dual_wan_info()

        assert dual_wan.wan0_enable is True
        assert dual_wan.wan1_enable is True
        assert dual_wan.wans_mode == WanMode.LOAD_BALANCE
        assert dual_wan.wan_origins[0] == DualWanOrigin.WAN
        assert dual_wan.wan_origins[1] == DualWanOrigin.LAN


class TestRouterClientGetWanConnectionInfo:
    """Tests for get_wan_connection_info method."""

    def test_get_wan_connection_info(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(WAN_STATE_NVRAM_RESPONSE)

        conn_info = client.get_wan_connection_info(0)

        assert conn_info.state == WanState.CONNECTED
        assert conn_info.substate == WanSubState.OK
        assert conn_info.auxstate == WanAuxState.CONNECTED
        assert conn_info.link_internet == LinkInternet.ONLINE
        assert conn_info.is_connected is True


class TestRouterClientGetSupportedFeatures:
    """Tests for get_supported_features method."""

    def test_get_supported_features(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(UI_SUPPORT_RESPONSE)

        caps = client.get_supported_features()

        assert caps.is_supported("dualwan") is True
        assert caps.is_supported("2.4G") is True
        assert caps.is_supported("5G") is True
        assert caps.is_supported("reboot_schedule") is True


class TestRouterClientGetPortStatusInfos:
    """Tests for get_port_status_infos method."""

    def test_get_port_status_infos(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(PORT_STATUS_RESPONSE)

        ports = client.get_port_status_infos("04:42:1A:0F:9E:D0")

        assert len(ports) == 5
        # Check WAN port
        wan_port = next(p for p in ports if p.id == "W0")
        assert wan_port.plugged is True
        assert wan_port.max_supported_speed_rate_mbps == 1000
        assert wan_port.current_speed_rate_mbps == 1000

        # Check LAN port with slow speed
        l1_port = next(p for p in ports if p.id == "L1")
        assert l1_port.plugged is True
        assert l1_port.max_supported_speed_rate_mbps == 1000
        assert l1_port.current_speed_rate_mbps == 100
        assert l1_port.is_slow_speed is True


class TestRouterClientGetPluggedUsbDevices:
    """Tests for get_plugged_usb_devices method."""

    def test_get_plugged_usb_devices(self):
        client, session = create_client_with_mock_session()
        session.get.return_value = create_mock_response(SHOW_USB_PATH_RESPONSE)

        devices = client.get_plugged_usb_devices()

        assert len(devices) == 2
        assert "storage" in [d.value for d in devices]
        assert "modem" in [d.value for d in devices]


class TestRouterClientParseSchedule:
    """Tests for _parse_schedule static method."""

    def test_parse_schedule(self):
        # "10001000400" = weekday mask "1000100", hour "04", minute "00"
        schedule = RouterClient._parse_schedule("10001000400")

        assert schedule.weekday_mask == 68  # binary 1000100
        assert schedule.hh == 4
        assert schedule.mm == 0


class TestRouterClientHandleResponse:
    """Tests for _handle_response instance method."""

    def test_handle_response_success(self):
        client = RouterClient(host="http://test", session=requests.Session())
        response = create_mock_response('{"data": "value"}')
        result = client._handle_response(response)
        assert result == '{"data": "value"}'

    def test_handle_response_auth_error(self):
        client = RouterClient(host="http://test", session=requests.Session())
        response = create_mock_response(LOGIN_ERROR_RESPONSE)
        with pytest.raises(AuthenticationError):
            client._handle_response(response)
