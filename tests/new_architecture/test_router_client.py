"""
Tests for the RouterClient module.
"""

import sys

sys.path.insert(0, "src")

import json
from unittest.mock import MagicMock, patch

import pytest

from asus_router_exporter.client.models import (
    ClientAmeshRole,
    DslTransMode,
    LinkInternet,
    SwMode,
    WanAuxState,
    WanDslProtoType,
    WanMode,
    WanState,
    WanSubState,
)
from asus_router_exporter.client.router_client import RouterClient, RouterClientFactory
from asus_router_exporter.core.exceptions import AuthenticationError


class TestRouterClientFactory:
    """Tests for RouterClientFactory."""

    def test_factory_adds_http_prefix(self):
        factory = RouterClientFactory("192.168.1.1")
        assert factory.host == "http://192.168.1.1"

    def test_factory_keeps_http_prefix(self):
        factory = RouterClientFactory("http://192.168.1.1")
        assert factory.host == "http://192.168.1.1"

    def test_factory_keeps_https_prefix(self):
        factory = RouterClientFactory("https://192.168.1.1")
        assert factory.host == "https://192.168.1.1"

    def test_factory_strips_trailing_slash(self):
        factory = RouterClientFactory("http://192.168.1.1/")
        assert factory.host == "http://192.168.1.1"

    @patch("requests.Session")
    def test_factory_auth_creates_client(self, mock_session_cls):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "token123"}'
        mock_session.post.return_value = mock_response
        mock_session_cls.return_value = mock_session

        factory = RouterClientFactory("192.168.1.1")
        client = factory.auth("admin:password")

        assert isinstance(client, RouterClient)
        assert client.host == "http://192.168.1.1"
        mock_session.post.assert_called_once()


class TestRouterClientReauth:
    """Tests for RouterClient re-authentication."""

    def test_reauthenticate_without_token_raises(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session, _auth_token="")

        with pytest.raises(AuthenticationError, match="no auth token stored"):
            client._reauthenticate()

    @patch("requests.Session")
    def test_reauthenticate_with_token_creates_new_session(self, mock_session_cls):
        old_session = MagicMock()
        new_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "new_token"}'
        new_session.post.return_value = mock_response
        mock_session_cls.return_value = new_session

        client = RouterClient(host="http://192.168.1.1", session=old_session, _auth_token="base64token")
        client._reauthenticate()

        assert client.session is new_session
        new_session.post.assert_called_once()


class TestRouterClientRequestWithReauth:
    """Tests for _request_with_reauth method."""

    def test_request_success_no_reauth(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session, _auth_token="token")

        mock_func = MagicMock(return_value="result")
        result = client._request_with_reauth(mock_func, "arg1", "arg2")

        assert result == "result"
        mock_func.assert_called_once_with("arg1", "arg2")

    @patch("requests.Session")
    def test_request_reauth_on_auth_error(self, mock_session_cls):
        old_session = MagicMock()
        new_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "new_token"}'
        new_session.post.return_value = mock_response
        mock_session_cls.return_value = new_session

        client = RouterClient(host="http://192.168.1.1", session=old_session, _auth_token="token")

        call_count = 0

        def mock_func(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise AuthenticationError("Session expired")
            return "success"

        result = client._request_with_reauth(mock_func)

        assert result == "success"
        assert call_count == 2

    def test_request_no_reauth_without_token(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session, _auth_token="")

        def mock_func():
            raise AuthenticationError("Session expired")

        with pytest.raises(AuthenticationError):
            client._request_with_reauth(mock_func)


class TestRouterClientHandleResponse:
    """Tests for _handle_response method."""

    def test_handle_response_success(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": "value"}'

        result = client._handle_response(mock_response)
        assert result == '{"data": "value"}'

    def test_handle_response_auth_error(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"error_status": "2"}'
        mock_response.json.return_value = {"error_status": "2"}

        with pytest.raises(AuthenticationError, match="session expired"):
            client._handle_response(mock_response)

    def test_handle_response_non_json(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "not json"
        mock_response.json.side_effect = json.decoder.JSONDecodeError("", "", 0)

        # Should not raise
        result = client._handle_response(mock_response)
        assert result == "not json"


class TestRouterClientGetSwMode:
    """Tests for get_sw_mode method."""

    def _create_client_with_nvram(self, nvram_response):
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(nvram_response)
        session.get.return_value = mock_response

        return RouterClient(host="http://192.168.1.1", session=session)

    def test_sw_mode_router(self):
        client = self._create_client_with_nvram({"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"})
        assert client.get_sw_mode() == SwMode.RT

    def test_sw_mode_repeater_mode2(self):
        client = self._create_client_with_nvram({"sw_mode": "2", "wlc_psta": "0", "wlc_express": "0"})
        assert client.get_sw_mode() == SwMode.RE

    def test_sw_mode_repeater_mode3(self):
        client = self._create_client_with_nvram({"sw_mode": "3", "wlc_psta": "2", "wlc_express": "0"})
        assert client.get_sw_mode() == SwMode.RE

    def test_sw_mode_access_point(self):
        client = self._create_client_with_nvram({"sw_mode": "3", "wlc_psta": "0", "wlc_express": "0"})
        assert client.get_sw_mode() == SwMode.AP

    def test_sw_mode_media_bridge(self):
        client = self._create_client_with_nvram({"sw_mode": "3", "wlc_psta": "1", "wlc_express": "0"})
        assert client.get_sw_mode() == SwMode.MB

    def test_sw_mode_expressway_2g(self):
        client = self._create_client_with_nvram({"sw_mode": "2", "wlc_psta": "0", "wlc_express": "1"})
        assert client.get_sw_mode() == SwMode.EW2

    def test_sw_mode_expressway_5g(self):
        client = self._create_client_with_nvram({"sw_mode": "2", "wlc_psta": "0", "wlc_express": "2"})
        assert client.get_sw_mode() == SwMode.EW5

    def test_sw_mode_hotspot(self):
        client = self._create_client_with_nvram({"sw_mode": "5", "wlc_psta": "0", "wlc_express": "0"})
        assert client.get_sw_mode() == SwMode.HS


class TestRouterClientWanInfo:
    """Tests for WAN info methods."""

    def _create_mock_client(self):
        session = MagicMock()
        return RouterClient(host="http://192.168.1.1", session=session, _auth_token="token")

    def test_get_wan_connection_info(self):
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(
            {"wan0_state_t": "2", "wan0_sbstate_t": "0", "wan0_auxstate_t": "0", "link_internet": "2"}
        )
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)
        info = client.get_wan_connection_info(0)

        assert info.state == WanState.CONNECTED
        assert info.substate == WanSubState.OK
        assert info.auxstate == WanAuxState.CONNECTED
        assert info.link_internet == LinkInternet.ONLINE


class TestRouterClientDualWan:
    """Tests for dual WAN methods."""

    def test_get_dual_wan_info(self):
        session = MagicMock()

        # Mock nvram response
        nvram_response = MagicMock()
        nvram_response.status_code = 200
        nvram_response.text = json.dumps(
            {"wans_dualwan": "wan lan", "wan0_enable": "1", "wan1_enable": "1", "wans_mode": "fo"}
        )

        # Mock get_wan_unit response
        wan_unit_response = MagicMock()
        wan_unit_response.status_code = 200
        wan_unit_response.text = '{"get_wan_unit": 0}'

        # Mock get_ui_support response
        ui_support_response = MagicMock()
        ui_support_response.status_code = 200
        ui_support_response.text = '{"get_ui_support": {"dualwan": "1"}}'

        session.get.side_effect = [nvram_response, wan_unit_response, ui_support_response]

        client = RouterClient(host="http://192.168.1.1", session=session)
        info = client.get_dual_wan_info()

        assert info.enabled is True
        assert info.wans_mode == WanMode.FAIL_OVER
        assert info.active_wan_unit == 0


class TestRouterClientDslInfo:
    """Tests for DSL info methods."""

    def test_get_dsl_info(self):
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"dsl0_proto": "pppoe", "dslx_transmode": "ptm"})
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)
        info = client.get_dsl_info()

        assert info.proto == WanDslProtoType.PPPoE
        assert info.transmode == DslTransMode.PTM


class TestRouterClientPortStatus:
    """Tests for port status methods."""

    def test_get_port_status_infos(self):
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(
            {
                "port_info": {
                    "AA:BB:CC:DD:EE:FF": {
                        "L1": {"is_on": "1", "cap": "2", "max_rate": "1000", "link_rate": "1000"},
                        "L2": {"is_on": "0", "cap": "2", "max_rate": "1000", "link_rate": "0"},
                    }
                }
            }
        )
        mock_response.json.return_value = {
            "port_info": {
                "AA:BB:CC:DD:EE:FF": {
                    "L1": {"is_on": "1", "cap": "2", "max_rate": "1000", "link_rate": "1000"},
                    "L2": {"is_on": "0", "cap": "2", "max_rate": "1000", "link_rate": "0"},
                }
            }
        }
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)
        ports = client.get_port_status_infos("AA:BB:CC:DD:EE:FF")

        assert len(ports) == 2
        assert ports[0].plugged is True
        assert ports[0].current_speed_rate_mbps == 1000


class TestRouterClientClients:
    """Tests for client listing methods."""

    def _mock_clients_response(self, session):
        # Mock get_ui_support
        ui_support_response = MagicMock()
        ui_support_response.status_code = 200
        ui_support_response.text = (
            '{"get_ui_support": {"stainfo": "1", "amas": "1", "force_roaming": "1", "sta_ap_bind": "1"}}'
        )

        # Mock get_clientlist
        clientlist_response = MagicMock()
        clientlist_response.status_code = 200
        clientlist_response.text = json.dumps(
            {
                "get_clientlist": {
                    "AA:BB:CC:DD:EE:FF": {
                        "name": "MyDevice",
                        "nickName": "Device",
                        "ip": "192.168.1.100",
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "vendor": "Apple",
                        "isWL": "1",
                        "isOnline": "1",
                        "opMode": "0",
                        "rssi": "-50",
                        "ipMethod": "DHCP",
                        "internetMode": "allow",
                        "internetState": "1",
                        "totalTx": "1000",
                        "totalRx": "2000",
                        "curTx": "100",
                        "curRx": "200",
                        "wlConnectTime": "3600",
                        "amesh_isReClient": "0",
                        "amesh_isRe": "0",
                        "amesh_papMac": "",
                        "amesh_bind_band": "0",
                        "amesh_bind_mac": "",
                    }
                }
            }
        )

        # Mock get_clientlist_from_json_database
        clientdb_response = MagicMock()
        clientdb_response.status_code = 200
        clientdb_response.text = json.dumps(
            {
                "get_clientlist_from_json_database": {
                    "AA:BB:CC:DD:EE:FF": {
                        "name": "MyDevice",
                        "nickName": "Device",
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "vendor": "Apple",
                        "online": "1",
                        "os_type": "1",
                        "type": "2",
                        "conn_ts": "1704067200",
                        "is_wireless": "1",
                        "amesh_isRe": "0",
                        "amesh_bind_band": "0",
                        "amesh_bind_mac": "",
                    }
                }
            }
        )

        session.get.side_effect = [ui_support_response, clientlist_response, clientdb_response]

    def test_get_clients(self):
        session = MagicMock()
        self._mock_clients_response(session)

        client = RouterClient(host="http://192.168.1.1", session=session)
        clients = client.get_clients()

        assert len(clients) == 1
        assert clients[0].mac == "AA:BB:CC:DD:EE:FF"
        assert clients[0].name == "MyDevice"


class TestRouterClientMapClientInfo:
    """Tests for _map_client_info and _map_client_info_from_db methods."""

    def _create_client(self):
        session = MagicMock()
        return RouterClient(host="http://192.168.1.1", session=session)

    def _create_caps(self, features: dict):
        from asus_router_exporter.client.models import RouterFeatureCapabilities

        return RouterFeatureCapabilities(features)

    def test_map_client_info_basic(self):
        client = self._create_client()
        caps = self._create_caps({"stainfo": "1", "amas": "1", "force_roaming": "1", "sta_ap_bind": "1"})

        client_data = {
            "name": "Device",
            "nickName": "Nick",
            "ip": "192.168.1.100",
            "mac": "AA:BB:CC:DD:EE:FF",
            "vendor": "Apple",
            "isWL": "1",
            "isOnline": "1",
            "opMode": "0",
            "rssi": "-50",
            "ipMethod": "DHCP",
            "internetMode": "allow",
            "internetState": "1",
            "totalTx": "1000",
            "totalRx": "2000",
            "curTx": "100",
            "curRx": "200",
            "wlConnectTime": "3600",
            "amesh_isReClient": "0",
            "amesh_isRe": "0",
            "amesh_papMac": "",
            "amesh_bind_band": "0",
            "amesh_bind_mac": "",
        }
        client_db_data = {"conn_ts": "1704067200", "is_wireless": "1", "os_type": "1", "type": "2"}

        info = client._map_client_info(caps, client_data, client_db_data)

        assert info.name == "Device"
        assert info.mac == "AA:BB:CC:DD:EE:FF"
        assert info.online is True
        assert info.rssi == -50
        assert info.throughput_info is not None
        assert info.throughput_info.total_upload_bytes == 1000

    def test_map_client_info_re_client(self):
        client = self._create_client()
        caps = self._create_caps({"stainfo": "1", "amas": "1", "force_roaming": "1", "sta_ap_bind": "1"})

        client_data = {
            "name": "Device",
            "nickName": "Nick",
            "ip": "192.168.1.100",
            "mac": "AA:BB:CC:DD:EE:FF",
            "vendor": "Apple",
            "isWL": "1",
            "isOnline": "1",
            "opMode": "0",
            "rssi": "-50",
            "ipMethod": "DHCP",
            "internetMode": "allow",
            "internetState": "1",
            "totalTx": "",
            "totalRx": "",
            "curTx": "",
            "curRx": "",
            "wlConnectTime": "",
            "amesh_isReClient": "1",
            "amesh_isRe": "0",
            "amesh_papMac": "11:22:33:44:55:66",
            "amesh_bind_band": "0",
            "amesh_bind_mac": "",
        }
        client_db_data = {"conn_ts": "1704067200", "is_wireless": "1", "os_type": "1", "type": "2"}

        info = client._map_client_info(caps, client_data, client_db_data)

        assert info.amesh_info is not None
        assert info.amesh_info.role == ClientAmeshRole.CLIENT
        assert info.amesh_info.pap_mac == "11:22:33:44:55:66"

    def test_map_client_info_re(self):
        client = self._create_client()
        caps = self._create_caps({"stainfo": "1", "amas": "1"})

        client_data = {
            "name": "RE Node",
            "nickName": "Repeater",
            "ip": "192.168.1.50",
            "mac": "AA:BB:CC:DD:EE:FF",
            "vendor": "ASUS",
            "isWL": "1",
            "isOnline": "1",
            "opMode": "0",
            "rssi": "-40",
            "ipMethod": "DHCP",
            "internetMode": "allow",
            "internetState": "1",
            "totalTx": "",
            "totalRx": "",
            "curTx": "",
            "curRx": "",
            "wlConnectTime": "",
            "amesh_isReClient": "0",
            "amesh_isRe": "1",
            "amesh_papMac": "",
        }
        client_db_data = {"conn_ts": "1704067200", "is_wireless": "1", "os_type": "0", "type": "0"}

        info = client._map_client_info(caps, client_data, client_db_data)

        assert info.amesh_info is not None
        assert info.amesh_info.role == ClientAmeshRole.REPEATER

    def test_map_client_info_from_db(self):
        client = self._create_client()
        caps = self._create_caps({"amas": "1", "force_roaming": "1", "sta_ap_bind": "1"})

        client_db_data = {
            "name": "Device",
            "nickName": "Nick",
            "mac": "AA:BB:CC:DD:EE:FF",
            "vendor": "Apple",
            "online": "0",
            "os_type": "1",
            "type": "2",
            "conn_ts": "1704067200",
            "is_wireless": "1",
            "amesh_isRe": "0",
            "amesh_bind_band": "1",
            "amesh_bind_mac": "11:22:33:44:55:66",
        }

        info = client._map_client_info_from_db(caps, client_db_data)

        assert info.name == "Device"
        assert info.mac == "AA:BB:CC:DD:EE:FF"
        assert info.online is False
        assert info.amesh_info is not None


class TestRouterClientRebootSchedule:
    """Tests for reboot schedule methods."""

    def test_parse_schedule(self):
        # Schedule format: first 7 chars are weekday binary mask, then 2-digit hour, then 2-digit minute
        # "1111111" (all days), "03" hour, "00" minute
        schedule = "11111110300"
        result = RouterClient._parse_schedule(schedule)

        assert result.weekday_mask == 127  # All 7 bits set (1111111 in binary)
        assert result.hh == 3
        assert result.mm == 0

    def test_parse_schedule_specific_days(self):
        # Schedule: weekday mask "1010101", hour 05, minute 30
        schedule = "10101010530"
        result = RouterClient._parse_schedule(schedule)

        assert result.weekday_mask == 85  # 1010101 in binary = 85
        assert result.hh == 5
        assert result.mm == 30


class TestRouterClientIntegration:
    """Integration tests for RouterClient."""

    def test_client_lifecycle(self):
        """Test basic client creation and method calls."""
        session = MagicMock()

        # Mock a simple nvram response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"}'
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session, _auth_token="token")

        # Test sw_mode
        mode = client.get_sw_mode()
        assert mode == SwMode.RT
