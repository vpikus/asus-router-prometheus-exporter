"""
Tests for the RouterClient module.
"""

import sys

sys.path.insert(0, "src")

import json
from unittest.mock import MagicMock, patch

import pytest

from asus_router_exporter.client import RouterClient, RouterClientFactory
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
    WifiAuthMode,
    WifiBand,
    WifiCrypto,
    WifiMfp,
    WifiMode,
    WifiUnit,
    WifiWpsWep,
)
from asus_router_exporter.core.exceptions import (
    AccountLockedError,
    AuthenticationBlockedError,
    AuthenticationError,
    CaptchaRequiredError,
    InvalidCredentialsError,
    SessionExpiredError,
)


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
                raise SessionExpiredError("Session expired")
            return "success"

        result = client._request_with_reauth(mock_func)

        assert result == "success"
        assert call_count == 2

    def test_request_no_reauth_without_token(self):
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session, _auth_token="")

        def mock_func():
            raise SessionExpiredError("Session expired")

        with pytest.raises(SessionExpiredError):
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

    def test_handle_response_returns_text(self):
        """_handle_response should return response text without JSON parsing."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"error_status": "2"}'

        # _handle_response no longer parses JSON or checks for errors
        # Auth error checking is now done by _parse_json_response
        result = client._handle_response(mock_response)
        assert result == '{"error_status": "2"}'

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


class TestCheckForErrorResponse:
    """Tests for _check_for_error_response method."""

    def test_check_error_response_with_error_status(self):
        """Should raise SessionExpiredError for error_status=2."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        error_response = '{"error_status":"2", "captcha_on":"0", "last_time_lock_warning":"0"}'
        with pytest.raises(SessionExpiredError):
            client._check_for_error_response(error_response)

    def test_check_error_response_no_error(self):
        """Should not raise for valid data without error_status."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        valid_response = '{"uptime": "Mon, 01 Jan 2024 12:00:00 +0000 (12345 secs)"}'
        # Should not raise
        client._check_for_error_response(valid_response)

    def test_check_error_response_error_status_zero(self):
        """Should not raise for error_status=0 (success)."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        success_response = '{"error_status":"0", "captcha_on":"0"}'
        # Should not raise
        client._check_for_error_response(success_response)

    def test_check_error_response_non_json(self):
        """Should not raise for non-JSON responses (e.g., JavaScript from ajax_coretmp.asp)."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        js_response = 'var curr_cpuTemp = "45.0"; var wifi_temp = "50.0";'
        # Should not raise
        client._check_for_error_response(js_response)

    def test_check_error_response_invalid_credentials(self):
        """Should raise InvalidCredentialsError for error_status=3."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        error_response = '{"error_status":"3", "captcha_on":"0"}'
        with pytest.raises(InvalidCredentialsError):
            client._check_for_error_response(error_response)


class TestParseJsonResponse:
    """Tests for _parse_json_response method."""

    def test_parse_json_response_valid_data(self):
        """Should parse and return valid JSON data."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        response = '{"key": "value", "number": 42}'
        result = client._parse_json_response(response)
        assert result == {"key": "value", "number": 42}

    def test_parse_json_response_with_error_status(self):
        """Should raise SessionExpiredError for error response."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        error_response = '{"error_status":"2", "captcha_on":"0"}'
        with pytest.raises(SessionExpiredError):
            client._parse_json_response(error_response)

    def test_parse_json_response_invalid_json(self):
        """Should raise JSONDecodeError for invalid JSON."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        invalid_json = "not valid json"
        with pytest.raises(json.JSONDecodeError):
            client._parse_json_response(invalid_json)

    def test_parse_json_response_error_status_zero(self):
        """Should return data when error_status is 0 (success)."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        response = '{"error_status":"0", "data": "some_value"}'
        result = client._parse_json_response(response)
        assert result == {"error_status": "0", "data": "some_value"}

    def test_parse_json_response_with_captcha_required(self):
        """Should raise CaptchaRequiredError when captcha_on=1."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        error_response = '{"error_status":"2", "captcha_on":"1"}'
        with pytest.raises(CaptchaRequiredError):
            client._parse_json_response(error_response)


class TestAuthenticationExceptions:
    """Tests for authentication exception handling based on error_status values."""

    def _create_auth_error_text(self, error_status: str, captcha_on: str = "0") -> tuple[RouterClient, str]:
        """Create a client and error response text with error_status and captcha_on.

        The router always returns both error_status and captcha_on in error responses,
        so we include both fields to match real router behavior.
        """
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        response_data = {"error_status": error_status, "captcha_on": captcha_on}
        response_text = json.dumps(response_data)

        return client, response_text

    def test_error_status_1_raises_session_expired(self):
        """error_status 1 should raise SessionExpiredError (recoverable)."""
        client, response_text = self._create_auth_error_text("1")
        with pytest.raises(SessionExpiredError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is True

    def test_error_status_2_raises_session_expired(self):
        """error_status 2 should raise SessionExpiredError (recoverable)."""
        client, response_text = self._create_auth_error_text("2")
        with pytest.raises(SessionExpiredError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is True

    def test_error_status_3_raises_invalid_credentials(self):
        """error_status 3 should raise InvalidCredentialsError (not recoverable)."""
        client, response_text = self._create_auth_error_text("3")
        with pytest.raises(InvalidCredentialsError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is False

    def test_error_status_7_raises_invalid_credentials(self):
        """error_status 7 should raise InvalidCredentialsError (not recoverable)."""
        client, response_text = self._create_auth_error_text("7")
        with pytest.raises(InvalidCredentialsError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is False

    def test_error_status_11_raises_account_locked(self):
        """error_status 11 should raise AccountLockedError (not recoverable)."""
        client, response_text = self._create_auth_error_text("11")
        with pytest.raises(AccountLockedError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is False

    def test_error_status_4_raises_auth_blocked(self):
        """error_status 4 should raise AuthenticationBlockedError (not recoverable)."""
        client, response_text = self._create_auth_error_text("4")
        with pytest.raises(AuthenticationBlockedError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is False
        assert exc_info.value.error_status == 4

    def test_error_status_unknown_raises_auth_blocked(self):
        """Unknown error_status (>11) should raise AuthenticationBlockedError."""
        client, response_text = self._create_auth_error_text("99")
        with pytest.raises(AuthenticationBlockedError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.error_status == 99

    def test_captcha_takes_priority_over_error_status(self):
        """captcha_on=1 should raise CaptchaRequiredError even with error_status <= 2."""
        client, response_text = self._create_auth_error_text("2", captcha_on="1")
        with pytest.raises(CaptchaRequiredError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is False

    def test_captcha_required_even_with_error_status_zero(self):
        """captcha_on=1 should raise CaptchaRequiredError even when error_status=0 (no error)."""
        client, response_text = self._create_auth_error_text("0", captcha_on="1")
        with pytest.raises(CaptchaRequiredError) as exc_info:
            client._parse_json_response(response_text)
        assert exc_info.value.recoverable is False

    def test_empty_error_status_treated_as_zero(self):
        """Empty error_status string should be treated as 0 (no error)."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        response_text = '{"error_status": "", "data": "value"}'

        # Should not raise - empty string treated as 0
        result = client._parse_json_response(response_text)
        assert "data" in result

    @patch("requests.Session")
    def test_non_recoverable_error_does_not_trigger_reauth(self, mock_session_cls):
        """Non-recoverable errors should not trigger re-authentication."""
        old_session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=old_session, _auth_token="token")

        def mock_func():
            raise InvalidCredentialsError("Bad credentials")

        # Should raise immediately without attempting re-auth
        with pytest.raises(InvalidCredentialsError):
            client._request_with_reauth(mock_func)

        # Verify no new session was created (no re-auth attempted)
        mock_session_cls.assert_not_called()


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


class TestRouterClientCache:
    """Tests for RouterClient caching behavior."""

    def test_clear_cache(self):
        """Test that clear_cache empties the cache dict."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        # Manually set cache values
        client._cache["test_key"] = "test_value"
        assert "test_key" in client._cache

        client.clear_cache()

        assert len(client._cache) == 0

    def test_get_sw_mode_caches_result(self):
        """Test that get_sw_mode caches its result."""
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"}'
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)

        # First call should hit the API
        result1 = client.get_sw_mode()
        assert result1 == SwMode.RT
        assert session.get.call_count == 1

        # Second call should use cache
        result2 = client.get_sw_mode()
        assert result2 == SwMode.RT
        assert session.get.call_count == 1  # No additional API call

    def test_get_sw_mode_after_clear_cache(self):
        """Test that get_sw_mode calls API again after cache is cleared."""
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"}'
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)

        # First call
        client.get_sw_mode()
        assert session.get.call_count == 1

        # Clear cache
        client.clear_cache()

        # Second call should hit API again
        client.get_sw_mode()
        assert session.get.call_count == 2

    def test_get_supported_features_caches_result(self):
        """Test that get_supported_features caches its result."""
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"get_ui_support": {"dualwan": "1", "2.4G": "1", "5G": "1"}}'
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)

        # First call should hit the API
        caps1 = client.get_supported_features()
        assert caps1.is_supported("dualwan") is True
        assert session.get.call_count == 1

        # Second call should use cache
        caps2 = client.get_supported_features()
        assert caps2.is_supported("dualwan") is True
        assert session.get.call_count == 1  # No additional API call

    def test_get_uptime_caches_result(self):
        """Test that get_uptime caches its result."""
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"uptime": "Mon, 01 Jan 2024 10:00:00 +0000(12345 secs since boot)"}'
        session.get.return_value = mock_response

        client = RouterClient(host="http://192.168.1.1", session=session)

        # First call should hit the API
        uptime1 = client.get_uptime()
        assert uptime1.boottime == 12345
        assert session.get.call_count == 1

        # Second call should use cache
        uptime2 = client.get_uptime()
        assert uptime2.boottime == 12345
        assert session.get.call_count == 1  # No additional API call

    def test_get_dual_wan_info_caches_result(self):
        """Test that get_dual_wan_info caches its result."""
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

        # First call should hit the API
        info1 = client.get_dual_wan_info()
        assert info1.enabled is True
        initial_call_count = session.get.call_count

        # Second call should use cache (no additional API calls)
        info2 = client.get_dual_wan_info()
        assert info2.enabled is True
        assert session.get.call_count == initial_call_count

    def test_multiple_cached_methods_share_cache(self):
        """Test that different cached methods use the same cache dict."""
        session = MagicMock()

        # Mock response for sw_mode
        sw_mode_response = MagicMock()
        sw_mode_response.status_code = 200
        sw_mode_response.text = '{"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"}'

        # Mock response for uptime
        uptime_response = MagicMock()
        uptime_response.status_code = 200
        uptime_response.text = '{"uptime": "Mon, 01 Jan 2024 10:00:00 +0000(12345 secs since boot)"}'

        session.get.side_effect = [sw_mode_response, uptime_response]

        client = RouterClient(host="http://192.168.1.1", session=session)

        # Call both methods
        client.get_sw_mode()
        client.get_uptime()

        # Both should be cached
        assert "sw_mode" in client._cache
        assert "uptime" in client._cache

        # Clear cache should clear both
        client.clear_cache()
        assert len(client._cache) == 0

    def test_cache_initialized_empty(self):
        """Test that a new client has an empty cache."""
        session = MagicMock()
        client = RouterClient(host="http://192.168.1.1", session=session)

        assert client._cache == {}


class TestProactiveReauthentication:
    """Tests for proactive re-authentication feature."""

    def test_needs_reauthentication_disabled_when_interval_zero(self):
        """Proactive re-auth should be disabled when interval is 0."""
        session = MagicMock()
        client = RouterClient(
            host="http://192.168.1.1",
            session=session,
            _auth_token="token",
            _reauth_interval_seconds=0,
        )
        assert client.needs_reauthentication() is False

    def test_needs_reauthentication_disabled_when_no_token(self):
        """Proactive re-auth should be disabled when no token is stored."""
        session = MagicMock()
        client = RouterClient(
            host="http://192.168.1.1",
            session=session,
            _auth_token="",
            _reauth_interval_seconds=1800,
        )
        assert client.needs_reauthentication() is False

    def test_needs_reauthentication_true_when_no_auth_time(self):
        """Should return True when auth time is not set (edge case)."""
        session = MagicMock()
        client = RouterClient(
            host="http://192.168.1.1",
            session=session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=None,
        )
        assert client.needs_reauthentication() is True

    def test_needs_reauthentication_false_when_not_elapsed(self):
        """Should return False when interval has not elapsed."""
        import time

        session = MagicMock()
        client = RouterClient(
            host="http://192.168.1.1",
            session=session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=time.monotonic(),  # Just authenticated
        )
        assert client.needs_reauthentication() is False

    def test_needs_reauthentication_true_when_elapsed(self):
        """Should return True when interval has elapsed."""
        import time

        session = MagicMock()
        # Auth happened 31 minutes ago, interval is 30 minutes
        past_auth_time = time.monotonic() - (31 * 60)  # 31 minutes in seconds
        client = RouterClient(
            host="http://192.168.1.1",
            session=session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=past_auth_time,
        )
        assert client.needs_reauthentication() is True

    @patch("requests.Session")
    def test_check_and_reauthenticate_does_nothing_when_not_needed(self, mock_session_cls):
        """check_and_reauthenticate should return False when re-auth not needed."""
        import time

        session = MagicMock()
        client = RouterClient(
            host="http://192.168.1.1",
            session=session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=time.monotonic(),
        )

        result = client.check_and_reauthenticate()

        assert result is False
        mock_session_cls.assert_not_called()

    @patch("requests.Session")
    def test_check_and_reauthenticate_performs_reauth_when_needed(self, mock_session_cls):
        """check_and_reauthenticate should re-authenticate when interval elapsed."""
        import time

        old_session = MagicMock()
        new_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "new_token"}'
        new_session.post.return_value = mock_response
        mock_session_cls.return_value = new_session

        past_auth_time = time.monotonic() - (31 * 60)  # 31 minutes in seconds
        client = RouterClient(
            host="http://192.168.1.1",
            session=old_session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=past_auth_time,
        )

        result = client.check_and_reauthenticate()

        assert result is True
        assert client.session is new_session
        new_session.post.assert_called_once()

    @patch("requests.Session")
    def test_reauthenticate_updates_last_auth_time(self, mock_session_cls):
        """_reauthenticate should update _last_auth_time."""
        import time

        old_session = MagicMock()
        new_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "new_token"}'
        new_session.post.return_value = mock_response
        mock_session_cls.return_value = new_session

        old_auth_time = time.monotonic() - 3600  # 1 hour in seconds
        client = RouterClient(
            host="http://192.168.1.1",
            session=old_session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=old_auth_time,
        )

        client._reauthenticate()

        assert client._last_auth_time is not None
        assert client._last_auth_time > old_auth_time

    @patch("asus_router_exporter.metrics.self_metrics.SelfMetrics.get_instance")
    @patch("requests.Session")
    def test_check_and_reauthenticate_propagates_auth_errors_without_recording_metric(
        self, mock_session_cls, mock_get_instance
    ):
        """Non-recoverable auth errors should propagate and NOT record proactive_reauth metric."""
        import time

        from asus_router_exporter.core.exceptions import InvalidCredentialsError

        old_session = MagicMock()
        new_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulate invalid credentials error response
        mock_response.text = '{"error_status": "7"}'
        mock_response.json.return_value = {"error_status": "7"}
        new_session.post.return_value = mock_response
        mock_session_cls.return_value = new_session

        mock_metrics = MagicMock()
        mock_get_instance.return_value = mock_metrics

        past_auth_time = time.monotonic() - (31 * 60)  # 31 minutes in seconds
        client = RouterClient(
            host="http://192.168.1.1",
            session=old_session,
            _auth_token="token",
            _reauth_interval_seconds=1800,
            _last_auth_time=past_auth_time,
        )

        # Should raise InvalidCredentialsError and NOT call record_proactive_reauth
        with pytest.raises(InvalidCredentialsError):
            client.check_and_reauthenticate()

        # Verify record_proactive_reauth was NOT called since re-auth failed
        mock_metrics.record_proactive_reauth.assert_not_called()

    def test_factory_sets_reauth_interval(self):
        """Factory should accept and use reauth_interval."""
        from asus_router_exporter.client.factory import DEFAULT_REAUTH_INTERVAL

        factory = RouterClientFactory("192.168.1.1")
        assert factory.reauth_interval == DEFAULT_REAUTH_INTERVAL

        factory_custom = RouterClientFactory("192.168.1.1", reauth_interval=3600)
        assert factory_custom.reauth_interval == 3600

    def test_factory_rejects_negative_reauth_interval(self):
        """Factory should raise ValueError for negative reauth_interval."""
        with pytest.raises(ValueError, match="reauth_interval must be non-negative"):
            RouterClientFactory("192.168.1.1", reauth_interval=-1)

    @patch("requests.Session")
    def test_factory_creates_client_with_reauth_interval(self, mock_session_cls):
        """Factory.auth should create client with configured reauth_interval."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "token123"}'
        mock_session.post.return_value = mock_response
        mock_session_cls.return_value = mock_session

        factory = RouterClientFactory("192.168.1.1", reauth_interval=3600)
        client = factory.auth("admin:password")

        assert client._reauth_interval_seconds == 3600
        assert client._last_auth_time is not None

    @patch("requests.Session")
    def test_factory_creates_client_with_zero_interval_disables_proactive_reauth(self, mock_session_cls):
        """Creating client with reauth_interval=0 should disable proactive re-auth."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"asus_token": "token123"}'
        mock_session.post.return_value = mock_response
        mock_session_cls.return_value = mock_session

        factory = RouterClientFactory("192.168.1.1", reauth_interval=0)
        client = factory.auth("admin:password")

        assert client._reauth_interval_seconds == 0
        assert client.needs_reauthentication() is False


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


class TestRouterClientWirelessInfo:
    """Tests for wireless info methods with JSON to DTO mapping."""

    def _create_client_with_responses(self, *responses):
        """Create a client with mocked session returning given responses in order."""
        session = MagicMock()
        mock_responses = []
        for response_data in responses:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = json.dumps(response_data)
            mock_responses.append(mock_response)
        session.get.side_effect = mock_responses
        return RouterClient(host="http://192.168.1.1", session=session)

    # -------------------------------------------------------------------------
    # get_wl_nband_info tests
    # -------------------------------------------------------------------------

    def test_get_wl_nband_info_single_2g_band(self):
        """Test parsing single 2.4G band."""
        client = self._create_client_with_responses({"wl_nband_info": [2]})
        result = client.get_wl_nband_info()

        assert result[WifiBand._2G] == 1
        assert result[WifiBand._5G] == 0
        assert result[WifiBand._6G] == 0

    def test_get_wl_nband_info_dual_band(self):
        """Test parsing dual band (2.4G + 5G)."""
        client = self._create_client_with_responses({"wl_nband_info": [2, 1]})
        result = client.get_wl_nband_info()

        assert result[WifiBand._2G] == 1
        assert result[WifiBand._5G] == 1
        assert result[WifiBand._6G] == 0

    def test_get_wl_nband_info_tri_band(self):
        """Test parsing tri-band (2.4G + dual 5G)."""
        client = self._create_client_with_responses({"wl_nband_info": [2, 1, 1]})
        result = client.get_wl_nband_info()

        assert result[WifiBand._2G] == 1
        assert result[WifiBand._5G] == 2  # Two 5G bands
        assert result[WifiBand._6G] == 0

    def test_get_wl_nband_info_wifi6e(self):
        """Test parsing WiFi 6E with 6G band."""
        client = self._create_client_with_responses({"wl_nband_info": [2, 1, 4]})
        result = client.get_wl_nband_info()

        assert result[WifiBand._2G] == 1
        assert result[WifiBand._5G] == 1
        assert result[WifiBand._6G] == 1

    def test_get_wl_nband_info_empty(self):
        """Test parsing empty band info."""
        client = self._create_client_with_responses({"wl_nband_info": []})
        result = client.get_wl_nband_info()

        assert result[WifiBand._2G] == 0
        assert result[WifiBand._5G] == 0
        assert result[WifiBand._6G] == 0

    # -------------------------------------------------------------------------
    # get_wireless_band_info tests
    # -------------------------------------------------------------------------

    def test_get_wireless_band_info_2g_basic(self):
        """Test parsing 2.4G band info from nvram."""
        nvram_data = {
            "wl0_ssid": "MyNetwork",
            "wl0_hwaddr": "AA:BB:CC:DD:EE:FF",
            "wl0_nmode_x": "0",  # AUTO
            "wl0_auth_mode_x": "psk2",
            "wl0_crypto": "aes",
            "wl0_mfp": "0",  # DISABLE
            "wl0_wep_x": "0",  # NONE
            "wl0_closed": "0",  # Not hidden
            "wl0_mbo_enable": "1",
        }
        client = self._create_client_with_responses(nvram_data)
        result = client.get_wireless_band_info(WifiUnit.WL_2G, repeater=False)

        assert result.ssid == "MyNetwork"
        assert result.mac == "AA:BB:CC:DD:EE:FF"
        assert result.mode == WifiMode.AUTO
        assert result.auth_mode == WifiAuthMode.PSK2
        assert result.crypto == WifiCrypto.AES
        assert result.mfp == WifiMfp.DISABLE
        assert result.wep == WifiWpsWep.NONE
        assert result.hidden_ssid is False
        assert result.mbo_enabled is True

    def test_get_wireless_band_info_5g_hidden_ssid(self):
        """Test parsing 5G band with hidden SSID."""
        nvram_data = {
            "wl1_ssid": "HiddenNetwork",
            "wl1_hwaddr": "11:22:33:44:55:66",
            "wl1_nmode_x": "8",  # MIXED
            "wl1_auth_mode_x": "sae",
            "wl1_crypto": "aes",
            "wl1_mfp": "2",  # REQUIRED
            "wl1_wep_x": "0",
            "wl1_closed": "1",  # Hidden
            "wl1_mbo_enable": "0",
        }
        client = self._create_client_with_responses(nvram_data)
        result = client.get_wireless_band_info(WifiUnit.WL_5G, repeater=False)

        assert result.ssid == "HiddenNetwork"
        assert result.mac == "11:22:33:44:55:66"
        assert result.mode == WifiMode.MIXED
        assert result.auth_mode == WifiAuthMode.SAE
        assert result.mfp == WifiMfp.REQUIRED
        assert result.hidden_ssid is True
        assert result.mbo_enabled is False

    def test_get_wireless_band_info_repeater_mode(self):
        """Test parsing band info in repeater mode (uses .1 suffix)."""
        nvram_data = {
            "wl0.1_ssid": "RepeaterNetwork",
            "wl0.1_hwaddr": "AA:AA:AA:AA:AA:AA",
            "wl0.1_nmode_x": "1",  # N_ONLY
            "wl0.1_auth_mode_x": "pskpsk2",
            "wl0.1_crypto": "tkip+aes",
            "wl0.1_mfp": "1",  # CAPABLE
            "wl0.1_wep_x": "0",
            "wl0.1_closed": "0",
            "wl0.1_mbo_enable": "0",
        }
        client = self._create_client_with_responses(nvram_data)
        result = client.get_wireless_band_info(WifiUnit.WL_2G, repeater=True)

        assert result.ssid == "RepeaterNetwork"
        assert result.mode == WifiMode.N_ONLY
        assert result.auth_mode == WifiAuthMode.PSKPSK2
        assert result.crypto == WifiCrypto.TKIP_AES
        assert result.mfp == WifiMfp.CAPABLE

    def test_get_wireless_band_info_mbo_enable_missing(self):
        """Test that missing mbo_enable defaults to False."""
        nvram_data = {
            "wl0_ssid": "Network",
            "wl0_hwaddr": "AA:BB:CC:DD:EE:FF",
            "wl0_nmode_x": "0",
            "wl0_auth_mode_x": "open",
            "wl0_crypto": "aes",
            "wl0_mfp": "0",
            "wl0_wep_x": "0",
            "wl0_closed": "0",
            # wl0_mbo_enable intentionally missing
        }
        client = self._create_client_with_responses(nvram_data)
        result = client.get_wireless_band_info(WifiUnit.WL_2G, repeater=False)

        assert result.mbo_enabled is False

    # -------------------------------------------------------------------------
    # get_wireless_info tests
    # -------------------------------------------------------------------------

    def test_get_wireless_info_dual_band_router_mode(self):
        """Test full wireless info collection for dual-band router."""
        session = MagicMock()

        # 1. get_wl_nband_info response
        nband_response = MagicMock()
        nband_response.status_code = 200
        nband_response.text = json.dumps({"wl_nband_info": [2, 1]})

        # 2. get_wireless_info nvram response (wps_enable, wlc_band, smart_connect_x)
        wireless_nvram = MagicMock()
        wireless_nvram.status_code = 200
        wireless_nvram.text = json.dumps(
            {
                "wps_enable": "1",
                "wlc_band": "0",
                "smart_connect_x": "1",
            }
        )

        # 3. get_supported_features response
        features_response = MagicMock()
        features_response.status_code = 200
        features_response.text = json.dumps(
            {"get_ui_support": {"2.4G": "1", "5G": "1", "5G-2": "0", "wifi6e": "0", "concurrep": "0"}}
        )

        # 4. get_sw_mode response
        sw_mode_response = MagicMock()
        sw_mode_response.status_code = 200
        sw_mode_response.text = json.dumps({"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"})

        # 5. 2.4G band info
        band_2g_response = MagicMock()
        band_2g_response.status_code = 200
        band_2g_response.text = json.dumps(
            {
                "wl0_ssid": "Home_2G",
                "wl0_hwaddr": "AA:BB:CC:DD:EE:01",
                "wl0_nmode_x": "0",
                "wl0_auth_mode_x": "psk2",
                "wl0_crypto": "aes",
                "wl0_mfp": "1",
                "wl0_wep_x": "0",
                "wl0_closed": "0",
                "wl0_mbo_enable": "1",
            }
        )

        # 6. 5G band info
        band_5g_response = MagicMock()
        band_5g_response.status_code = 200
        band_5g_response.text = json.dumps(
            {
                "wl1_ssid": "Home_5G",
                "wl1_hwaddr": "AA:BB:CC:DD:EE:02",
                "wl1_nmode_x": "8",
                "wl1_auth_mode_x": "sae",
                "wl1_crypto": "aes",
                "wl1_mfp": "2",
                "wl1_wep_x": "0",
                "wl1_closed": "1",
                "wl1_mbo_enable": "0",
            }
        )

        session.get.side_effect = [
            nband_response,
            wireless_nvram,
            features_response,
            sw_mode_response,
            band_2g_response,
            band_5g_response,
        ]

        client = RouterClient(host="http://192.168.1.1", session=session)
        result = client.get_wireless_info()

        # Verify top-level WifiInfo
        assert result.wps_enabled is True
        assert result.smart_connect_enabled is True
        assert result.bands_count[WifiBand._2G] == 1
        assert result.bands_count[WifiBand._5G] == 1

        # Verify 2.4G band
        assert result.band_2G_info is not None
        assert result.band_2G_info.ssid == "Home_2G"
        assert result.band_2G_info.auth_mode == WifiAuthMode.PSK2
        assert result.band_2G_info.hidden_ssid is False

        # Verify 5G band
        assert result.band_5G_info is not None
        assert result.band_5G_info.ssid == "Home_5G"
        assert result.band_5G_info.auth_mode == WifiAuthMode.SAE
        assert result.band_5G_info.hidden_ssid is True

        # No 5G-2 or 6G
        assert result.band_5G_2_info is None
        assert result.band_6G_info is None

    def test_get_wireless_info_single_band(self):
        """Test wireless info for single 2.4G band router."""
        session = MagicMock()

        nband_response = MagicMock()
        nband_response.status_code = 200
        nband_response.text = json.dumps({"wl_nband_info": [2]})

        wireless_nvram = MagicMock()
        wireless_nvram.status_code = 200
        wireless_nvram.text = json.dumps(
            {
                "wps_enable": "0",
                "wlc_band": "0",
                "smart_connect_x": "0",
            }
        )

        features_response = MagicMock()
        features_response.status_code = 200
        features_response.text = json.dumps(
            {"get_ui_support": {"2.4G": "1", "5G": "0", "5G-2": "0", "wifi6e": "0", "concurrep": "0"}}
        )

        sw_mode_response = MagicMock()
        sw_mode_response.status_code = 200
        sw_mode_response.text = json.dumps({"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"})

        band_2g_response = MagicMock()
        band_2g_response.status_code = 200
        band_2g_response.text = json.dumps(
            {
                "wl0_ssid": "BasicWifi",
                "wl0_hwaddr": "AA:BB:CC:DD:EE:FF",
                "wl0_nmode_x": "2",  # LEGACY
                "wl0_auth_mode_x": "open",
                "wl0_crypto": "aes",
                "wl0_mfp": "0",
                "wl0_wep_x": "0",
                "wl0_closed": "0",
            }
        )

        session.get.side_effect = [
            nband_response,
            wireless_nvram,
            features_response,
            sw_mode_response,
            band_2g_response,
        ]

        client = RouterClient(host="http://192.168.1.1", session=session)
        result = client.get_wireless_info()

        assert result.wps_enabled is False
        assert result.smart_connect_enabled is False
        assert result.band_2G_info is not None
        assert result.band_2G_info.ssid == "BasicWifi"
        assert result.band_2G_info.mode == WifiMode.LEGACY
        assert result.band_2G_info.auth_mode == WifiAuthMode.OPEN
        assert result.band_5G_info is None
        assert result.band_5G_2_info is None
        assert result.band_6G_info is None

    def test_get_wireless_info_repeater_mode(self):
        """Test wireless info in repeater mode uses .1 suffix for correct band."""
        session = MagicMock()

        nband_response = MagicMock()
        nband_response.status_code = 200
        nband_response.text = json.dumps({"wl_nband_info": [2, 1]})

        wireless_nvram = MagicMock()
        wireless_nvram.status_code = 200
        wireless_nvram.text = json.dumps(
            {
                "wps_enable": "0",
                "wlc_band": "0",  # Connected to 2.4G
                "smart_connect_x": "0",
            }
        )

        features_response = MagicMock()
        features_response.status_code = 200
        features_response.text = json.dumps(
            {"get_ui_support": {"2.4G": "1", "5G": "1", "5G-2": "0", "wifi6e": "0", "concurrep": "0"}}
        )

        # Repeater mode
        sw_mode_response = MagicMock()
        sw_mode_response.status_code = 200
        sw_mode_response.text = json.dumps({"sw_mode": "2", "wlc_psta": "0", "wlc_express": "0"})

        # 2.4G in repeater mode uses .1 suffix (wlc_band=0 and not concurrep)
        band_2g_response = MagicMock()
        band_2g_response.status_code = 200
        band_2g_response.text = json.dumps(
            {
                "wl0.1_ssid": "Repeater_2G",
                "wl0.1_hwaddr": "AA:BB:CC:DD:EE:01",
                "wl0.1_nmode_x": "0",
                "wl0.1_auth_mode_x": "psk2",
                "wl0.1_crypto": "aes",
                "wl0.1_mfp": "0",
                "wl0.1_wep_x": "0",
                "wl0.1_closed": "0",
            }
        )

        # 5G not in repeater mode (wlc_band=0, not 1)
        band_5g_response = MagicMock()
        band_5g_response.status_code = 200
        band_5g_response.text = json.dumps(
            {
                "wl1_ssid": "Normal_5G",
                "wl1_hwaddr": "AA:BB:CC:DD:EE:02",
                "wl1_nmode_x": "0",
                "wl1_auth_mode_x": "psk2",
                "wl1_crypto": "aes",
                "wl1_mfp": "0",
                "wl1_wep_x": "0",
                "wl1_closed": "0",
            }
        )

        session.get.side_effect = [
            nband_response,
            wireless_nvram,
            features_response,
            sw_mode_response,
            band_2g_response,
            band_5g_response,
        ]

        client = RouterClient(host="http://192.168.1.1", session=session)
        result = client.get_wireless_info()

        # 2.4G should use repeater SSID
        assert result.band_2G_info.ssid == "Repeater_2G"
        # 5G should use normal SSID
        assert result.band_5G_info.ssid == "Normal_5G"

    def test_get_wireless_info_wifi6e(self):
        """Test wireless info with WiFi 6E (6G band)."""
        session = MagicMock()

        nband_response = MagicMock()
        nband_response.status_code = 200
        nband_response.text = json.dumps({"wl_nband_info": [2, 1, 4]})

        wireless_nvram = MagicMock()
        wireless_nvram.status_code = 200
        wireless_nvram.text = json.dumps(
            {
                "wps_enable": "1",
                "wlc_band": "0",
                "smart_connect_x": "1",
            }
        )

        features_response = MagicMock()
        features_response.status_code = 200
        features_response.text = json.dumps(
            {"get_ui_support": {"2.4G": "1", "5G": "1", "5G-2": "0", "wifi6e": "1", "concurrep": "0"}}
        )

        sw_mode_response = MagicMock()
        sw_mode_response.status_code = 200
        sw_mode_response.text = json.dumps({"sw_mode": "1", "wlc_psta": "0", "wlc_express": "0"})

        band_2g_response = MagicMock()
        band_2g_response.status_code = 200
        band_2g_response.text = json.dumps(
            {
                "wl0_ssid": "Home_2G",
                "wl0_hwaddr": "AA:BB:CC:DD:EE:01",
                "wl0_nmode_x": "0",
                "wl0_auth_mode_x": "psk2sae",
                "wl0_crypto": "aes",
                "wl0_mfp": "1",
                "wl0_wep_x": "0",
                "wl0_closed": "0",
            }
        )

        band_5g_response = MagicMock()
        band_5g_response.status_code = 200
        band_5g_response.text = json.dumps(
            {
                "wl1_ssid": "Home_5G",
                "wl1_hwaddr": "AA:BB:CC:DD:EE:02",
                "wl1_nmode_x": "9",  # AX_ONLY
                "wl1_auth_mode_x": "sae",
                "wl1_crypto": "aes",
                "wl1_mfp": "2",
                "wl1_wep_x": "0",
                "wl1_closed": "0",
            }
        )

        # 6G band (wl3)
        band_6g_response = MagicMock()
        band_6g_response.status_code = 200
        band_6g_response.text = json.dumps(
            {
                "wl3_ssid": "Home_6G",
                "wl3_hwaddr": "AA:BB:CC:DD:EE:03",
                "wl3_nmode_x": "9",
                "wl3_auth_mode_x": "sae",
                "wl3_crypto": "aes",
                "wl3_mfp": "2",
                "wl3_wep_x": "0",
                "wl3_closed": "0",
            }
        )

        session.get.side_effect = [
            nband_response,
            wireless_nvram,
            features_response,
            sw_mode_response,
            band_2g_response,
            band_5g_response,
            band_6g_response,
        ]

        client = RouterClient(host="http://192.168.1.1", session=session)
        result = client.get_wireless_info()

        assert result.bands_count[WifiBand._2G] == 1
        assert result.bands_count[WifiBand._5G] == 1
        assert result.bands_count[WifiBand._6G] == 1

        assert result.band_2G_info is not None
        assert result.band_2G_info.auth_mode == WifiAuthMode.PSK2SAE

        assert result.band_5G_info is not None
        assert result.band_5G_info.mode == WifiMode.AX_ONLY

        assert result.band_6G_info is not None
        assert result.band_6G_info.ssid == "Home_6G"
        assert result.band_6G_info.auth_mode == WifiAuthMode.SAE
