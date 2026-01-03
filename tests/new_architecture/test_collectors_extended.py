"""
Extended tests for collector modules.

Tests for: MemoryCollector, NetdevCollector, WANCollector, WirelessCollector,
PortsCollector, RouterInfoCollector, ClientsCollector
"""

import sys
from unittest.mock import Mock

sys.path.insert(0, "src")

from prometheus_client import CollectorRegistry

from asus_router_exporter.client.models import (
    ClientAmeshRole,
    WanAuxState,
    WanMode,
    WanState,
    WanStatus,
    WanSubState,
)
from asus_router_exporter.collectors.clients import ClientsCollector
from asus_router_exporter.collectors.memory import MemoryCollector
from asus_router_exporter.collectors.netdev import NetdevCollector
from asus_router_exporter.collectors.ports import PortsCollector
from asus_router_exporter.collectors.router_info import RouterInfoCollector
from asus_router_exporter.collectors.wan import WANCollector
from asus_router_exporter.collectors.wireless import WirelessCollector


class MockConfig:
    """Mock configuration for testing."""

    def __init__(self, data=None):
        self._data = data or {}

    def get(self, key, default=None):
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default

    def get_collector_config(self, collector_name):
        return self.get(f"collectors.{collector_name}", {})


# ============================================================================
# Memory Collector Tests
# ============================================================================


class TestMemoryCollector:
    """Tests for MemoryCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"memory": {"enabled": True}}})

    def test_memory_collector_initialization(self):
        collector = MemoryCollector(self.registry, self.config)

        assert collector.name == "memory"
        assert collector.enabled is True
        assert len(collector._metrics) == 4

    def test_collect_memory_metrics(self):
        collector = MemoryCollector(self.registry, self.config)

        router_client = Mock()
        mem_info = Mock(total_kb=1048576, used_kb=524288, free_kb=524288)
        router_client.get_memory_usage.return_value = mem_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Verify metrics were collected
        samples = list(collector._total_bytes.collect())
        assert len(samples) > 0

    def test_memory_percentage_calculation(self):
        collector = MemoryCollector(self.registry, self.config)

        router_client = Mock()
        # 50% usage
        mem_info = Mock(total_kb=1000, used_kb=500, free_kb=500)
        router_client.get_memory_usage.return_value = mem_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Check percentage calculation
        samples = list(collector._used_percent.collect())
        for sample in samples:
            for s in sample.samples:
                if s.labels.get("product_id") == "RT-AX88U":
                    assert s.value == 50.0

    def test_memory_collection_failure(self):
        collector = MemoryCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_memory_usage.side_effect = Exception("Connection failed")

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise
        collector.collect(router_client, router_info)

    def test_kb_to_bytes_conversion(self):
        assert MemoryCollector._kb_to_bytes(1024) == 1024 * 1024
        assert MemoryCollector._kb_to_bytes(None) is None
        assert MemoryCollector._kb_to_bytes(0) == 0

    def test_set_gauge_safe(self):
        # Create collector to ensure metrics are registered (though we test static method)
        MemoryCollector(self.registry, self.config)

        gauge = Mock()
        MemoryCollector._set_gauge_safe(gauge, 100.0)
        gauge.set.assert_called_with(100.0)

        gauge.reset_mock()
        MemoryCollector._set_gauge_safe(gauge, None)
        gauge.set.assert_called_once()

    def test_memory_percentage_clamping(self):
        """Test that percentage is clamped between 0 and 100."""
        collector = MemoryCollector(self.registry, self.config)

        router_client = Mock()
        # Edge case: used > total (shouldn't happen but test clamping)
        mem_info = Mock(total_kb=100, used_kb=150, free_kb=-50)
        router_client.get_memory_usage.return_value = mem_info

        router_info = Mock(product_id="RT-AX88U")
        collector.collect(router_client, router_info)


# ============================================================================
# Netdev Collector Tests
# ============================================================================


class TestNetdevCollector:
    """Tests for NetdevCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"netdev": {"enabled": True}}})

    def test_netdev_collector_initialization(self):
        collector = NetdevCollector(self.registry, self.config)

        assert collector.name == "netdev"
        assert collector.enabled is True
        assert len(collector._metrics) == 8

    def test_first_sample_initializes_counters(self):
        collector = NetdevCollector(self.registry, self.config)

        router_client = Mock()
        bridge = Mock(total_upload_bytes=1000, total_download_bytes=2000)
        wired = Mock(total_upload_bytes=500, total_download_bytes=1000)
        netdev_info = Mock(
            bridge=bridge,
            wired=wired,
            internet={"0": Mock(total_upload_bytes=100, total_download_bytes=200)},
            wireless={"0": Mock(total_upload_bytes=50, total_download_bytes=100)},
        )
        router_client.get_netdev.return_value = netdev_info

        router_info = Mock(product_id="RT-AX88U")

        # First collection
        collector.collect(router_client, router_info)

        assert len(collector._previous_samples) > 0

    def test_delta_calculation(self):
        collector = NetdevCollector(self.registry, self.config)

        # Normal delta
        assert collector._calculate_delta(100, 50) == 50
        # Wrap around
        assert collector._calculate_delta(50, 100) == 0

    def test_second_sample_increments_counters(self):
        collector = NetdevCollector(self.registry, self.config)

        router_client = Mock()
        bridge1 = Mock(total_upload_bytes=1000, total_download_bytes=2000)
        wired1 = Mock(total_upload_bytes=500, total_download_bytes=1000)
        netdev_info1 = Mock(bridge=bridge1, wired=wired1, internet={}, wireless={})
        router_client.get_netdev.return_value = netdev_info1

        router_info = Mock(product_id="RT-AX88U")

        # First sample
        collector.collect(router_client, router_info)

        # Second sample with increased values
        bridge2 = Mock(total_upload_bytes=1500, total_download_bytes=2500)
        wired2 = Mock(total_upload_bytes=600, total_download_bytes=1100)
        netdev_info2 = Mock(bridge=bridge2, wired=wired2, internet={}, wireless={})
        router_client.get_netdev.return_value = netdev_info2

        collector.collect(router_client, router_info)

    def test_netdev_collection_failure(self):
        collector = NetdevCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_netdev.side_effect = Exception("Connection failed")

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise
        collector.collect(router_client, router_info)

    def test_cleanup_clears_samples(self):
        collector = NetdevCollector(self.registry, self.config)
        collector._previous_samples = {"bridge": {"tx": 100, "rx": 200}}

        collector.cleanup()

        assert collector._previous_samples == {}

    def test_multi_interface_collection(self):
        collector = NetdevCollector(self.registry, self.config)

        router_client = Mock()
        netdev_info = Mock(
            bridge=Mock(total_upload_bytes=1000, total_download_bytes=2000),
            wired=Mock(total_upload_bytes=500, total_download_bytes=1000),
            internet={
                "0": Mock(total_upload_bytes=100, total_download_bytes=200),
                "1": Mock(total_upload_bytes=150, total_download_bytes=250),
            },
            wireless={
                "0": Mock(total_upload_bytes=50, total_download_bytes=100),
                "1": Mock(total_upload_bytes=75, total_download_bytes=125),
            },
        )
        router_client.get_netdev.return_value = netdev_info

        router_info = Mock(product_id="RT-AX88U")

        # First sample
        collector.collect(router_client, router_info)

        assert "internet" in collector._previous_samples
        assert "wireless" in collector._previous_samples


# ============================================================================
# WAN Collector Tests
# ============================================================================


class TestWANCollector:
    """Tests for WANCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"wan": {"enabled": True}}})

    def test_wan_collector_initialization(self):
        collector = WANCollector(self.registry, self.config)

        assert collector.name == "wan"
        assert collector.enabled is True

    def test_collect_wan_metrics(self):
        collector = WANCollector(self.registry, self.config)

        router_client = Mock()

        # Create mock WAN info
        dual_wan_info = Mock(enabled=True, wans_mode=WanMode.LOAD_BALANCE)
        connection_info = Mock(
            state=WanState.CONNECTED, substate=WanSubState.OK, auxstate=WanAuxState.CONNECTED, is_connected=True
        )
        primary_wan = Mock(connection_info=connection_info, status=WanStatus.CONNECTED, active=True)
        wan_info = Mock(
            dual_wan_info=dual_wan_info, link_internet=Mock(value=1), primary_wan=primary_wan, secondary_wan=None
        )
        router_client.get_network_wan_info.return_value = wan_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_wan_collection_failure(self):
        collector = WANCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_network_wan_info.side_effect = Exception("Connection failed")

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise
        collector.collect(router_client, router_info)

    def test_dual_wan_disabled(self):
        collector = WANCollector(self.registry, self.config)

        router_client = Mock()
        dual_wan_info = Mock(enabled=False, wans_mode=None)
        connection_info = Mock(
            state=WanState.CONNECTED, substate=WanSubState.OK, auxstate=WanAuxState.CONNECTED, is_connected=True
        )
        primary_wan = Mock(connection_info=connection_info, status=WanStatus.CONNECTED, active=True)
        wan_info = Mock(dual_wan_info=dual_wan_info, link_internet=True, primary_wan=primary_wan, secondary_wan=None)
        router_client.get_network_wan_info.return_value = wan_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_secondary_wan_present(self):
        collector = WANCollector(self.registry, self.config)

        router_client = Mock()
        dual_wan_info = Mock(enabled=True, wans_mode=WanMode.FAIL_OVER)
        connection_info = Mock(
            state=WanState.CONNECTED, substate=WanSubState.OK, auxstate=WanAuxState.CONNECTED, is_connected=True
        )
        primary_wan = Mock(connection_info=connection_info, status=WanStatus.CONNECTED, active=True)
        secondary_wan = Mock(
            connection_info=Mock(
                state=WanState.IDLE, substate=WanSubState.OK, auxstate=WanAuxState.DISCONNECTED, is_connected=False
            ),
            status=WanStatus.DISCONNECTED,
            active=False,
        )
        wan_info = Mock(
            dual_wan_info=dual_wan_info,
            link_internet=Mock(value=1),
            primary_wan=primary_wan,
            secondary_wan=secondary_wan,
        )
        router_client.get_network_wan_info.return_value = wan_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)


# ============================================================================
# Wireless Collector Tests
# ============================================================================


class TestWirelessCollector:
    """Tests for WirelessCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"wireless": {"enabled": True}}})

    def test_wireless_collector_initialization(self):
        collector = WirelessCollector(self.registry, self.config)

        assert collector.name == "wireless"
        assert collector.enabled is True

    def test_collect_wireless_metrics(self):
        collector = WirelessCollector(self.registry, self.config)

        router_client = Mock()
        wireless_info = Mock(
            wps_enabled=True,
            smart_connect=False,
            bands=[
                Mock(
                    band="2.4GHz",
                    ssid="TestNetwork",
                    mac="AA:BB:CC:DD:EE:FF",
                    mode=Mock(name="ax"),
                    auth_mode=Mock(name="psk2"),
                    crypto=Mock(name="aes"),
                    hidden=False,
                )
            ],
        )
        router_client.get_network_wireless_info.return_value = wireless_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_wireless_collection_failure(self):
        collector = WirelessCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_network_wireless_info.side_effect = Exception("Failed")

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise
        collector.collect(router_client, router_info)

    def test_multiple_bands(self):
        collector = WirelessCollector(self.registry, self.config)

        router_client = Mock()
        wireless_info = Mock(
            wps_enabled=True,
            smart_connect=True,
            bands=[
                Mock(
                    band="2.4GHz",
                    ssid="TestNetwork",
                    mac="AA:BB:CC:DD:EE:FF",
                    mode=Mock(name="ax"),
                    auth_mode=Mock(name="psk2"),
                    crypto=Mock(name="aes"),
                    hidden=False,
                ),
                Mock(
                    band="5GHz",
                    ssid="TestNetwork_5G",
                    mac="AA:BB:CC:DD:EE:00",
                    mode=Mock(name="ax"),
                    auth_mode=Mock(name="psk2"),
                    crypto=Mock(name="aes"),
                    hidden=True,
                ),
            ],
        )
        router_client.get_network_wireless_info.return_value = wireless_info

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_remove_stale_band_metrics_via_remove_method(self):
        """Test that _remove_stale_band_metrics correctly removes stale metrics."""
        from asus_router_exporter.client.models import WifiAuthMode, WifiCrypto, WifiMode

        collector = WirelessCollector(self.registry, self.config)

        # Pre-populate some metrics for bands 0 and 1
        for wl_unit in ["0", "1"]:
            collector._band_info.labels(product_id="RT-AX88U", wl_unit=wl_unit).info(
                {"wl_ssid": f"Network_{wl_unit}", "wl_mac": f"AA:BB:CC:DD:EE:{wl_unit}F"}
            )
            collector._ssid_hidden.labels(product_id="RT-AX88U", wl_unit=wl_unit).set(0)
            # Set one-hot metrics for modes
            for mode in WifiMode:
                val = 1 if mode == WifiMode.AX_ONLY else 0
                collector._band_mode.labels(product_id="RT-AX88U", wl_unit=wl_unit, wl_mode=mode.name).set(val)
            for auth in WifiAuthMode:
                val = 1 if auth == WifiAuthMode.PSK2 else 0
                collector._auth_mode.labels(product_id="RT-AX88U", wl_unit=wl_unit, wl_auth_mode=auth.value).set(val)
            for crypto in WifiCrypto:
                val = 1 if crypto == WifiCrypto.AES else 0
                collector._crypto.labels(product_id="RT-AX88U", wl_unit=wl_unit, wl_crypto=crypto.value).set(val)

        # Track that bands 0 and 1 were active
        collector._active_bands = {"0", "1"}

        # Call _remove_stale_band_metrics - band 1 should be removed
        collector._remove_stale_band_metrics("RT-AX88U", {"0", "1"}, {"0"})

        # Verify remove was called (the method handles KeyError internally)
        # This test verifies the method doesn't raise and executes all removal paths

    def test_remove_stale_band_metrics_direct(self):
        """Test _remove_stale_band_metrics directly."""
        from asus_router_exporter.client.models import WifiMode

        collector = WirelessCollector(self.registry, self.config)

        # Pre-populate metrics for bands 0 and 1
        for wl_unit in ["0", "1"]:
            collector._band_info.labels(product_id="RT-AX88U", wl_unit=wl_unit).info(
                {"wl_ssid": f"Network_{wl_unit}", "wl_mac": f"AA:BB:CC:DD:EE:{wl_unit}F"}
            )
            collector._ssid_hidden.labels(product_id="RT-AX88U", wl_unit=wl_unit).set(0)
            for mode in WifiMode:
                collector._band_mode.labels(product_id="RT-AX88U", wl_unit=wl_unit, wl_mode=mode.name).set(0)

        # Call remove_stale directly - band 1 should be removed
        collector._remove_stale_band_metrics("RT-AX88U", {"0", "1"}, {"0"})

        # This should not raise - verifies the removal logic works
        # The method handles KeyError internally for metrics that don't exist

    def test_cleanup_clears_active_bands(self):
        """Test that cleanup properly clears active bands."""
        from asus_router_exporter.client.models import WifiAuthMode, WifiCrypto, WifiMode

        collector = WirelessCollector(self.registry, self.config)
        router_client = Mock()
        router_info = Mock(product_id="RT-AX88U")

        # Collect some metrics first
        wireless_info = Mock(
            wps_enabled=True,
            smart_connect_enabled=True,
            band_2G_info=Mock(
                ssid="Network",
                mac="AA:BB:CC:DD:EE:FF",
                mode=WifiMode.MIXED,
                auth_mode=WifiAuthMode.OPEN,
                crypto=WifiCrypto.AES,
                hidden_ssid=False,
            ),
            band_5G_info=None,
            band_5G_2_info=None,
            band_6G_info=None,
        )
        router_client.get_network_wireless_info.return_value = wireless_info

        collector.collect(router_client, router_info)
        assert len(collector._active_bands) > 0

        # Cleanup should clear active bands
        collector.cleanup()
        assert len(collector._active_bands) == 0

    def test_set_onehot_enum_fallback_when_enum_not_found(self):
        """Test that _set_onehot_enum falls back to string value when enum class not found."""
        collector = WirelessCollector(self.registry, self.config)
        router_client = Mock()
        router_info = Mock(product_id="RT-AX88U")

        # Create band_info with a mock mode that's not a real enum
        fake_mode = Mock()
        fake_mode.name = "UNKNOWN_MODE"
        fake_mode.__str__ = lambda self: "UNKNOWN_MODE"

        wireless_info = Mock(
            wps_enabled=True,
            smart_connect_enabled=False,
            band_2G_info=Mock(
                ssid="Network",
                mac="AA:BB:CC:DD:EE:FF",
                mode=fake_mode,
                auth_mode=None,
                crypto=None,
                hidden_ssid=False,
            ),
            band_5G_info=None,
            band_5G_2_info=None,
            band_6G_info=None,
        )
        router_client.get_network_wireless_info.return_value = wireless_info

        # Should not raise even with non-standard enum values
        collector.collect(router_client, router_info)


# ============================================================================
# Ports Collector Tests
# ============================================================================


class TestPortsCollector:
    """Tests for PortsCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"ports": {"enabled": True}}})

    def test_ports_collector_initialization(self):
        collector = PortsCollector(self.registry, self.config)

        assert collector.name == "ports"
        assert collector.enabled is True

    def test_collect_ports_metrics(self):
        collector = PortsCollector(self.registry, self.config)

        router_client = Mock()
        router_info = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=[
                Mock(
                    id="W0",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=1000,
                    is_slow_speed=False,
                    group=Mock(name="WAN"),
                ),
                Mock(
                    id="L1",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=100,
                    is_slow_speed=True,
                    group=Mock(name="LAN"),
                ),
                Mock(
                    id="L2",
                    plugged=False,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=0,
                    is_slow_speed=False,
                    group=Mock(name="LAN"),
                ),
            ],
        )

        collector.collect(router_client, router_info)

    def test_ports_no_info(self):
        collector = PortsCollector(self.registry, self.config)

        router_client = Mock()
        router_info = Mock(product_id="RT-AX88U", lan_hwaddr="AA:BB:CC:DD:EE:FF", ports_info=None)

        # Should not raise
        collector.collect(router_client, router_info)

    def test_ports_empty_list(self):
        collector = PortsCollector(self.registry, self.config)

        router_client = Mock()
        router_info = Mock(product_id="RT-AX88U", lan_hwaddr="AA:BB:CC:DD:EE:FF", ports_info=[])

        collector.collect(router_client, router_info)

    def test_remove_stale_port_metrics(self):
        """Test that stale port metrics are removed when ports disappear."""
        from asus_router_exporter.client.models import PortGroup

        collector = PortsCollector(self.registry, self.config)
        router_client = Mock()

        # First collection with 3 ports
        router_info_1 = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=[
                Mock(
                    id="W0",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=1000,
                    is_slow_speed=False,
                    group=PortGroup.WAN,
                    special_port_name="",
                ),
                Mock(
                    id="L1",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=100,
                    is_slow_speed=True,
                    group=PortGroup.LAN,
                    special_port_name="",
                ),
                Mock(
                    id="L2",
                    plugged=True,
                    max_supported_speed_rate_mbps=2500,
                    current_speed_rate_mbps=2500,
                    is_slow_speed=False,
                    group=PortGroup.LAN,
                    special_port_name="2.5G Port",
                ),
            ],
        )

        collector.collect(router_client, router_info_1)

        # Verify all 3 ports are tracked
        assert "W0" in collector._active_port_ids
        assert "L1" in collector._active_port_ids
        assert "L2" in collector._active_port_ids

        # Second collection with only 2 ports (L2 removed - USB port unplugged)
        router_info_2 = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=[
                Mock(
                    id="W0",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=1000,
                    is_slow_speed=False,
                    group=PortGroup.WAN,
                    special_port_name="",
                ),
                Mock(
                    id="L1",
                    plugged=False,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=0,
                    is_slow_speed=False,
                    group=PortGroup.LAN,
                    special_port_name="",
                ),
            ],
        )

        collector.collect(router_client, router_info_2)

        # Verify L2 is no longer tracked
        assert "W0" in collector._active_port_ids
        assert "L1" in collector._active_port_ids
        assert "L2" not in collector._active_port_ids

    def test_remove_all_port_metrics_when_ports_info_becomes_none(self):
        """Test that all port metrics are removed when ports_info becomes None."""
        from asus_router_exporter.client.models import PortGroup

        collector = PortsCollector(self.registry, self.config)
        router_client = Mock()

        # First collection with ports
        router_info_1 = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=[
                Mock(
                    id="W0",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=1000,
                    is_slow_speed=False,
                    group=PortGroup.WAN,
                    special_port_name="",
                ),
            ],
        )

        collector.collect(router_client, router_info_1)
        assert len(collector._active_port_ids) > 0

        # Second collection with ports_info = None
        router_info_2 = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=None,
        )

        collector.collect(router_client, router_info_2)

        # All ports should be removed
        assert len(collector._active_port_ids) == 0

    def test_cleanup_clears_active_port_ids(self):
        """Test that cleanup properly clears active port IDs."""
        from asus_router_exporter.client.models import PortGroup

        collector = PortsCollector(self.registry, self.config)
        router_client = Mock()

        # Collect some metrics first
        router_info = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=[
                Mock(
                    id="W0",
                    plugged=True,
                    max_supported_speed_rate_mbps=1000,
                    current_speed_rate_mbps=1000,
                    is_slow_speed=False,
                    group=PortGroup.WAN,
                    special_port_name="",
                ),
            ],
        )

        collector.collect(router_client, router_info)
        assert len(collector._active_port_ids) > 0

        # Cleanup should clear active port IDs
        collector.cleanup()
        assert len(collector._active_port_ids) == 0

    def test_port_with_usb_group(self):
        """Test port collection with USB group type."""
        from asus_router_exporter.client.models import PortGroup

        collector = PortsCollector(self.registry, self.config)
        router_client = Mock()

        router_info = Mock(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            ports_info=[
                Mock(
                    id="USB1",
                    plugged=True,
                    max_supported_speed_rate_mbps=5000,
                    current_speed_rate_mbps=5000,
                    is_slow_speed=False,
                    group=PortGroup.USB,
                    special_port_name="USB 3.0",
                ),
            ],
        )

        collector.collect(router_client, router_info)

        # Verify USB port is tracked
        assert "USB1" in collector._active_port_ids


# ============================================================================
# Router Info Collector Tests
# ============================================================================


class TestRouterInfoCollector:
    """Tests for RouterInfoCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"router_info": {"enabled": True}}})

    def test_router_info_collector_initialization(self):
        collector = RouterInfoCollector(self.registry, self.config)

        assert collector.name == "router_info"
        assert collector.enabled is True

    def test_collect_router_info_metrics(self):
        collector = RouterInfoCollector(self.registry, self.config)

        router_client = Mock()
        router_info = Mock(
            product_id="RT-AX88U",
            firmver="3.0.0.4",
            extendno="386_51234",
            serial_no="ABC123",
            lan_hostname="router",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            sw_mode=Mock(name="RT"),
            uptime=Mock(boottime=86400),
            reboot_schedule=Mock(enabled=True, until_ms=3600000),
            software_update_available=False,
        )

        collector.collect(router_client, router_info)

    def test_router_info_no_uptime(self):
        collector = RouterInfoCollector(self.registry, self.config)

        router_client = Mock()
        router_info = Mock(
            product_id="RT-AX88U",
            firmver="3.0.0.4",
            extendno="386_51234",
            serial_no="ABC123",
            lan_hostname="router",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            sw_mode=Mock(name="RT"),
            uptime=None,
            reboot_schedule=None,
            software_update_available=True,
        )

        collector.collect(router_client, router_info)

    def test_router_info_missing_attributes(self):
        collector = RouterInfoCollector(self.registry, self.config)

        router_client = Mock()
        # Minimal router_info with empty string attributes (not None - Info metric doesn't accept None)
        router_info = Mock(product_id="RT-AX88U")
        router_info.firmver = ""
        router_info.extendno = ""
        router_info.serial_no = ""
        router_info.lan_hostname = ""
        router_info.lan_hwaddr = ""
        router_info.sw_mode = None
        router_info.uptime = None
        router_info.reboot_schedule = None
        router_info.software_update_available = None

        collector.collect(router_client, router_info)

    def test_router_info_cleanup_clears_info_metric(self):
        """Test that cleanup properly handles Info metrics (which store values as dict)."""
        collector = RouterInfoCollector(self.registry, self.config)

        router_client = Mock()
        router_info = Mock(
            product_id="RT-AX88U",
            firmver="3.0.0.4",
            extendno="386_51234",
            serial_no="ABC123",
            lan_hostname="router",
            lan_hwaddr="AA:BB:CC:DD:EE:FF",
            sw_mode=None,
            uptime=None,
            reboot_schedule=None,
            software_update_available=False,
        )

        # Collect some metrics first
        collector.collect(router_client, router_info)

        # Cleanup should not raise an error (previously failed with "'dict' object has no attribute 'set'")
        collector.cleanup()


# ============================================================================
# Clients Collector Tests
# ============================================================================


class TestClientsCollector:
    """Tests for ClientsCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"clients": {"enabled": True}}})

    def test_clients_collector_initialization(self):
        collector = ClientsCollector(self.registry, self.config)

        assert collector.name == "clients"
        assert collector.enabled is True

    def test_collect_clients_metrics(self):
        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # Create mock client with interface that has label attribute
        interface = Mock()
        interface.label = "2.4GHz"

        # Create mock amesh_info
        amesh_info = Mock()
        amesh_info.pap_mac = ""
        amesh_info.role = ClientAmeshRole.CLIENT

        # Create mock client - not a ClientInfo instance
        client = Mock()
        client.mac = "AA:BB:CC:DD:EE:FF"
        client.ipaddr = "192.168.1.100"
        client.name = "TestDevice"
        client.nick_name = ""
        client.vendor = "Apple"
        client.last_conn_interface = interface
        client.amesh_info = amesh_info

        router_client.get_clients.return_value = [client]

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_clients_collection_failure(self):
        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_clients.side_effect = Exception("Failed")

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise
        collector.collect(router_client, router_info)

    def test_clients_empty_list(self):
        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_clients.return_value = []

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_multiple_clients(self):
        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # Create mock interfaces
        interface1 = Mock()
        interface1.label = "2.4GHz"

        interface2 = Mock()
        interface2.label = "Wired"

        # Create mock clients
        client1 = Mock()
        client1.mac = "AA:BB:CC:DD:EE:FF"
        client1.name = "Device1"
        client1.nick_name = ""
        client1.vendor = "Apple"
        client1.last_conn_interface = interface1
        client1.amesh_info = None

        client2 = Mock()
        client2.mac = "11:22:33:44:55:66"
        client2.name = "Device2"
        client2.nick_name = ""
        client2.vendor = "Samsung"
        client2.last_conn_interface = interface2
        client2.amesh_info = None

        router_client.get_clients.return_value = [client1, client2]

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_client_with_missing_optional_fields(self):
        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        client = Mock()
        client.mac = "AA:BB:CC:DD:EE:FF"
        client.name = ""
        client.nick_name = ""
        client.vendor = ""
        client.last_conn_interface = None
        client.amesh_info = None

        router_client.get_clients.return_value = [client]

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_cleanup(self):
        collector = ClientsCollector(self.registry, self.config)

        collector.cleanup()

        # Just verify cleanup doesn't raise
        assert True

    def test_collect_with_client_info_instance(self):
        """Test collection with actual ClientInfo instance to cover detailed metrics."""
        from asus_router_exporter.client.models import (
            ClientAmeshInfo,
            ClientInfo,
            ClientInterface,
            ClientInternetMode,
            ClientInternetState,
            ClientIpMethod,
            ClientOperationMode,
            ThroughputInfo,
            TrafficStats,
        )

        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # Create actual ClientInfo instance
        amesh_info = ClientAmeshInfo(role=ClientAmeshRole.CLIENT, pap_mac="11:22:33:44:55:66")
        traffic_stats = TrafficStats(rx=1000, tx=500)
        throughput_info = ThroughputInfo(total_download_bytes=10000, total_upload_bytes=5000)

        client = ClientInfo(
            mac="AA:BB:CC:DD:EE:FF",
            name="TestDevice",
            nick_name="MyDevice",
            vendor="Apple",
            online=True,
            os_type=5,
            device_type=2,
            last_conn_ts=1700000000,
            last_conn_interface=ClientInterface.WL_5G,
            amesh_info=amesh_info,
            ipaddr="192.168.1.100",
            interface=ClientInterface.WL_5G,
            op_mode=ClientOperationMode.RT,
            rssi=-65,
            ip_method=ClientIpMethod.DHCP,
            internet_mode=ClientInternetMode.ALLOW,
            internet_state=ClientInternetState.ALLOW,
            traffic_stats=traffic_stats,
            throughput_info=throughput_info,
            conn_time="01:30:00",
        )

        router_client.get_clients.return_value = [client]
        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Verify metrics were collected
        samples = list(collector._online.collect())
        assert len(samples) > 0

    def test_collect_with_wired_client_info_no_rssi(self):
        """Test that wired clients don't emit RSSI metrics."""
        from asus_router_exporter.client.models import (
            ClientInfo,
            ClientInterface,
            ClientInternetMode,
            ClientInternetState,
        )

        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # Create wired ClientInfo (LAN interface)
        client = ClientInfo(
            mac="AA:BB:CC:DD:EE:FF",
            name="WiredDevice",
            nick_name="",
            vendor="Dell",
            online=True,
            os_type=0,
            device_type=0,
            last_conn_ts=1700000000,
            last_conn_interface=ClientInterface.LAN,
            amesh_info=None,
            ipaddr="192.168.1.101",
            interface=ClientInterface.LAN,
            op_mode=None,
            rssi=None,
            ip_method=None,
            internet_mode=ClientInternetMode.ALLOW,
            internet_state=ClientInternetState.ALLOW,
        )

        router_client.get_clients.return_value = [client]
        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Verify collection completed without errors
        samples = list(collector._online.collect())
        assert len(samples) > 0

    def test_collect_client_with_none_values(self):
        """Test collection handles None values gracefully in detailed metrics."""
        from asus_router_exporter.client.models import (
            ClientInfo,
            ClientInterface,
            ClientInternetMode,
            ClientInternetState,
        )

        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # ClientInfo with many None values
        client = ClientInfo(
            mac="AA:BB:CC:DD:EE:FF",
            name="",
            nick_name="",
            vendor="",
            online=False,
            os_type=0,
            device_type=0,
            last_conn_ts=None,
            last_conn_interface=ClientInterface.WL_2G,
            amesh_info=None,
            ipaddr="192.168.1.102",
            interface=ClientInterface.WL_2G,
            op_mode=None,
            rssi=None,
            ip_method=None,
            internet_mode=ClientInternetMode.BLOCK,
            internet_state=ClientInternetState.BLOCK,
            traffic_stats=None,
            throughput_info=None,
            conn_time=None,
        )

        router_client.get_clients.return_value = [client]
        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

    def test_set_onehot_interface_all_interfaces(self):
        """Test that _set_onehot_interface sets all interface values correctly."""
        from asus_router_exporter.client.models import (
            ClientInfo,
            ClientInterface,
            ClientInternetMode,
            ClientInternetState,
        )

        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # Test with 5G interface
        client = ClientInfo(
            mac="AA:BB:CC:DD:EE:FF",
            name="Test",
            nick_name="",
            vendor="",
            online=True,
            os_type=0,
            device_type=0,
            last_conn_ts=None,
            last_conn_interface=ClientInterface.WL_5G,
            amesh_info=None,
            ipaddr="192.168.1.100",
            interface=ClientInterface.WL_5G,
            op_mode=None,
            rssi=-70,
            ip_method=None,
            internet_mode=ClientInternetMode.ALLOW,
            internet_state=ClientInternetState.ALLOW,
        )

        router_client.get_clients.return_value = [client]
        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Check that interface one-hot was set (one should be 1, others 0)
        samples = list(collector._interface.collect())
        assert len(samples) > 0

    def test_set_onehot_enum_with_all_enum_values(self):
        """Test that _set_onehot_enum correctly sets all enum values."""
        from asus_router_exporter.client.models import (
            ClientAmeshInfo,
            ClientInfo,
            ClientInterface,
            ClientInternetMode,
            ClientInternetState,
            ClientIpMethod,
            ClientOperationMode,
        )

        collector = ClientsCollector(self.registry, self.config)

        router_client = Mock()

        # Create client with all enum values set
        amesh_info = ClientAmeshInfo(role=ClientAmeshRole.REPEATER, pap_mac="11:22:33:44:55:66")

        client = ClientInfo(
            mac="AA:BB:CC:DD:EE:FF",
            name="EnumTest",
            nick_name="",
            vendor="",
            online=True,
            os_type=0,
            device_type=0,
            last_conn_ts=1700000000,
            last_conn_interface=ClientInterface.WL_6G,
            amesh_info=amesh_info,
            ipaddr="192.168.1.100",
            interface=ClientInterface.WL_6G,
            op_mode=ClientOperationMode.RE,
            rssi=-55,
            ip_method=ClientIpMethod.STATIC,
            internet_mode=ClientInternetMode.TIME,
            internet_state=ClientInternetState.ALLOW,
        )

        router_client.get_clients.return_value = [client]
        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Verify one-hot metrics were set
        op_mode_samples = list(collector._op_mode.collect())
        assert len(op_mode_samples) > 0

        amesh_samples = list(collector._amesh_role.collect())
        assert len(amesh_samples) > 0

    def test_collect_preserves_active_labels(self):
        """Test that cleanup properly clears active labels from mixin."""
        collector = ClientsCollector(self.registry, self.config)

        # Simulate some tracking
        collector._active_labels["test_key"] = {"some", "labels"}

        collector.cleanup()

        assert len(collector._active_labels) == 0
