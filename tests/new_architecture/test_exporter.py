"""
Tests for the Exporter module.
"""

import sys

sys.path.insert(0, "src")

import signal
from unittest.mock import MagicMock, patch

from prometheus_client import CollectorRegistry

from asus_router_exporter.core.config import Config
from asus_router_exporter.core.container import Container
from asus_router_exporter.server.exporter import Exporter, FallbackRouterInfo, create_exporter


class TestFallbackRouterInfo:
    """Tests for FallbackRouterInfo dataclass."""

    def test_default_values(self):
        info = FallbackRouterInfo()

        assert info.product_id == "unknown"
        assert info.lan_hwaddr == ""
        assert info.lan_hostname == ""
        assert info.firmver == ""
        assert info.extendno == ""
        assert info.serial_no == ""
        assert info.sw_mode is None
        assert info.uptime is None
        assert info.reboot_schedule is None
        assert info.software_update_available is False
        assert info.ports_info == []

    def test_custom_values(self):
        info = FallbackRouterInfo(product_id="RT-AX88U", lan_hwaddr="AA:BB:CC:DD:EE:FF")

        assert info.product_id == "RT-AX88U"
        assert info.lan_hwaddr == "AA:BB:CC:DD:EE:FF"


class TestExporterInit:
    """Tests for Exporter initialization."""

    def test_init_creates_status_metrics(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        # Check metrics are created
        assert exporter._up is not None
        assert exporter._scrape_duration is not None
        # Check shutdown event is not set (i.e., running state)
        assert not exporter._shutdown_event.is_set()

    def test_init_stores_container(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        assert exporter._container is container


class TestExporterCollectRouterInfo:
    """Tests for router info collection."""

    def test_collect_router_info_success(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.product_id = "RT-AX88U"
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._collect_router_info()

        assert exporter._router_info is mock_info
        mock_client.get_info.assert_called_once()

    def test_collect_router_info_failure_uses_fallback(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_client.get_info.side_effect = Exception("Connection failed")
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._collect_router_info()

        assert isinstance(exporter._router_info, FallbackRouterInfo)
        assert exporter._router_info.product_id == "unknown"


class TestExporterCollectWithErrorHandling:
    """Tests for collect_with_error_handling method."""

    def test_successful_collection_sets_up_to_1(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_error_handler = MagicMock()
        mock_error_handler.execute = MagicMock(side_effect=lambda fn: fn())

        with patch.object(container, "_error_handler", mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(exporter, "_collect_metrics"):
                exporter._collect_with_error_handling()

        # Check up metric was set to 1
        labels = exporter._up._metrics[("RT-AX88U",)]
        assert labels._value._value == 1

    def test_failed_collection_sets_up_to_0(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_error_handler = MagicMock()
        mock_error_handler.execute.side_effect = RuntimeError("Collection failed")

        with patch.object(container, "_error_handler", mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(container, "clear_all_metrics"):
                exporter._collect_with_error_handling()

        # Check up metric was set to 0
        labels = exporter._up._metrics[("RT-AX88U",)]
        assert labels._value._value == 0

    def test_failed_collection_clears_metrics(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_error_handler = MagicMock()
        mock_error_handler.execute.side_effect = RuntimeError("Collection failed")

        with patch.object(container, "_error_handler", mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(container, "clear_all_metrics") as mock_clear:
                exporter._collect_with_error_handling()
                mock_clear.assert_called_once()

    def test_scrape_duration_recorded(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_error_handler = MagicMock()
        mock_error_handler.execute = MagicMock(side_effect=lambda fn: fn())

        with patch.object(container, "_error_handler", mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(exporter, "_collect_metrics"):
                exporter._collect_with_error_handling()

        # Check duration metric was recorded
        labels = exporter._scrape_duration._metrics[("RT-AX88U",)]
        assert labels._value._value >= 0


class TestExporterCollectMetrics:
    """Tests for _collect_metrics method."""

    def test_collect_metrics_delegates_to_container(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._router_info = mock_info

        with patch.object(container, "collect_metrics") as mock_collect:
            exporter._collect_metrics()
            mock_collect.assert_called_once_with(mock_info)

    def test_collect_metrics_clears_cache_first(self):
        """Test that cache is cleared before refreshing router info."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Track call order to verify clear_cache is called before get_info
        call_order = []

        def record_clear_cache():
            call_order.append("clear_cache")

        def record_get_info():
            call_order.append("get_info")
            return mock_info

        mock_client.clear_cache.side_effect = record_clear_cache
        mock_client.get_info.side_effect = record_get_info

        exporter = Exporter(container)
        exporter._router_info = mock_info

        with patch.object(container, "collect_metrics"):
            exporter._collect_metrics()

        # Verify ordering: clear_cache must be called before get_info
        assert call_order == ["clear_cache", "get_info"], f"Expected clear_cache before get_info, got: {call_order}"

    def test_collect_metrics_refreshes_router_info(self):
        """Test that router info is refreshed on each collection cycle."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        # Return different info on each call
        initial_info = MagicMock(product_id="RT-AX88U", uptime=100)
        updated_info = MagicMock(product_id="RT-AX88U", uptime=200)
        # First call returns updated_info (the refresh during _collect_metrics)
        mock_client.get_info.return_value = updated_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        # Simulate that router_info was set to initial_info previously
        exporter._router_info = initial_info

        with patch.object(container, "collect_metrics") as mock_collect:
            exporter._collect_metrics()

            # Router info should be refreshed to updated_info
            assert exporter._router_info is updated_info
            # Container should receive the updated info
            mock_collect.assert_called_once_with(updated_info)

    def test_collect_metrics_keeps_previous_info_on_refresh_failure(self):
        """Test that previous router info is kept if refresh fails."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        initial_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.side_effect = Exception("Connection failed")
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._router_info = initial_info

        with patch.object(container, "collect_metrics") as mock_collect:
            exporter._collect_metrics()

            # Should still use previous info
            assert exporter._router_info is initial_info
            mock_collect.assert_called_once_with(initial_info)

    def test_cache_cleared_exactly_once_per_cycle(self):
        """Test that cache is cleared exactly once per collection cycle."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._router_info = mock_info

        with patch.object(container, "collect_metrics"):
            # Run multiple collection cycles
            for cycle in range(3):
                mock_client.clear_cache.reset_mock()
                exporter._collect_metrics()
                # Exactly one clear_cache call per cycle
                assert mock_client.clear_cache.call_count == 1, (
                    f"Cycle {cycle + 1}: Expected 1 clear_cache call, got {mock_client.clear_cache.call_count}"
                )

    def test_cache_cleared_even_with_no_enabled_collectors(self):
        """Test that cache is cleared even when no collectors are enabled."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Container has no registered collectors (simulates all disabled)
        container._initialized = True
        container._collectors = []

        exporter = Exporter(container)
        exporter._router_info = mock_info

        # _collect_metrics should still clear cache even with no collectors
        exporter._collect_metrics()

        mock_client.clear_cache.assert_called_once()


class TestExporterShutdown:
    """Tests for shutdown handling."""

    def test_handle_shutdown_sets_shutdown_event(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)
        assert not exporter._shutdown_event.is_set()

        exporter._handle_shutdown(signal.SIGINT, None)

        assert exporter._shutdown_event.is_set()
        assert exporter._received_signal == signal.SIGINT

    def test_shutdown_cleans_up_container(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        with patch.object(container, "cleanup") as mock_cleanup:
            exporter._shutdown()
            mock_cleanup.assert_called_once()


class TestExporterRun:
    """Tests for the run method."""

    @patch("asus_router_exporter.server.exporter.start_http_server")
    @patch("asus_router_exporter.server.exporter.signal.signal")
    def test_run_starts_http_server(self, mock_signal, mock_start_server):
        registry = CollectorRegistry()
        config = Config({"exporter": {"port": 9100, "scrape_interval": 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Mock start_http_server to return (HTTPServer, Thread) tuple
        mock_httpd = MagicMock()
        mock_start_server.return_value = (mock_httpd, MagicMock())

        exporter = Exporter(container)

        # Set shutdown event immediately to exit the loop
        exporter._shutdown_event.set()

        with patch.object(container, "cleanup"):
            exporter.run()

        mock_start_server.assert_called_once_with(9100, registry=registry)

    @patch("asus_router_exporter.server.exporter.start_http_server")
    @patch("asus_router_exporter.server.exporter.signal.signal")
    def test_run_registers_signal_handlers(self, mock_signal, mock_start_server):
        registry = CollectorRegistry()
        config = Config({"exporter": {"port": 8000, "scrape_interval": 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Mock start_http_server to return (HTTPServer, Thread) tuple
        mock_httpd = MagicMock()
        mock_start_server.return_value = (mock_httpd, MagicMock())

        exporter = Exporter(container)

        # Set shutdown event immediately to exit the loop
        exporter._shutdown_event.set()

        with patch.object(container, "cleanup"):
            exporter.run()

        # Check SIGINT and SIGTERM handlers were registered
        signal_calls = [call[0][0] for call in mock_signal.call_args_list]
        assert signal.SIGINT in signal_calls
        assert signal.SIGTERM in signal_calls

    @patch("asus_router_exporter.server.exporter.start_http_server")
    @patch("asus_router_exporter.server.exporter.signal.signal")
    def test_run_collects_router_info(self, mock_signal, mock_start_server):
        registry = CollectorRegistry()
        config = Config({"exporter": {"port": 8000, "scrape_interval": 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Mock start_http_server to return (HTTPServer, Thread) tuple
        mock_httpd = MagicMock()
        mock_start_server.return_value = (mock_httpd, MagicMock())

        exporter = Exporter(container)

        # Set shutdown event immediately to exit the loop
        exporter._shutdown_event.set()

        with patch.object(container, "cleanup"):
            exporter.run()

        # Router info should have been collected
        mock_client.get_info.assert_called_once()

    @patch("asus_router_exporter.server.exporter.start_http_server")
    @patch("asus_router_exporter.server.exporter.signal.signal")
    def test_run_cleanup_on_exit(self, mock_signal, mock_start_server):
        registry = CollectorRegistry()
        config = Config({"exporter": {"port": 8000, "scrape_interval": 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Mock start_http_server to return (HTTPServer, Thread) tuple
        mock_httpd = MagicMock()
        mock_start_server.return_value = (mock_httpd, MagicMock())

        exporter = Exporter(container)

        # Set shutdown event immediately to exit the loop
        exporter._shutdown_event.set()

        with patch.object(container, "cleanup") as mock_cleanup:
            exporter.run()
            mock_cleanup.assert_called_once()


class TestCreateExporter:
    """Tests for create_exporter factory function."""

    @patch("asus_router_exporter.server.exporter.Container")
    def test_create_exporter_from_env(self, mock_container_cls):
        mock_container = MagicMock()
        mock_container.config = Config.from_env()
        mock_container.registry = CollectorRegistry()
        mock_container_cls.from_env.return_value = mock_container

        exporter = create_exporter()

        mock_container_cls.from_env.assert_called_once()
        mock_container.register_collectors.assert_called_once()
        mock_container.initialize.assert_called_once()
        assert isinstance(exporter, Exporter)

    @patch("asus_router_exporter.server.exporter.Container")
    def test_create_exporter_from_config(self, mock_container_cls):
        mock_container = MagicMock()
        mock_container.config = Config.from_env()
        mock_container.registry = CollectorRegistry()
        mock_container_cls.from_config.return_value = mock_container

        exporter = create_exporter(config_path="config.yaml")

        mock_container_cls.from_config.assert_called_once_with("config.yaml")
        assert isinstance(exporter, Exporter)

    @patch("asus_router_exporter.server.exporter.Container")
    def test_create_exporter_with_overrides(self, mock_container_cls):
        mock_config = MagicMock()
        mock_container = MagicMock()
        mock_container.config = mock_config
        mock_container.registry = CollectorRegistry()
        mock_container_cls.from_env.return_value = mock_container

        # The exporter is created to verify the function runs and applies overrides
        create_exporter(router_host="10.0.0.1", router_auth="admin:pass", metrics_port=9100)

        # Check config overrides were applied
        mock_config.set.assert_any_call("router.host", "10.0.0.1")
        mock_config.set.assert_any_call("router.auth", "admin:pass")
        mock_config.set.assert_any_call("exporter.port", 9100)


class TestExporterIntegration:
    """Integration tests for Exporter."""

    def test_exporter_lifecycle_without_run(self):
        """Test exporter can be created and configured without running."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)

        # Manually collect router info
        exporter._collect_router_info()
        assert exporter._router_info is mock_info

        # Manually collect metrics
        with patch.object(container, "collect_metrics") as mock_collect:
            exporter._collect_metrics()
            mock_collect.assert_called_once_with(mock_info)


class TestNodeSwitchDetection:
    """Tests for AiMesh node switch detection."""

    def test_refresh_router_info_detects_node_switch(self):
        """Test that node switch is detected when product_id changes."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        old_info = MagicMock(product_id="RT-AX88U")
        new_info = MagicMock(product_id="RT-AX86U")
        mock_client.get_info.return_value = new_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._router_info = old_info
        exporter._previous_product_id = "RT-AX88U"

        with patch.object(exporter, "_handle_node_switch") as mock_handle:
            exporter._refresh_router_info(mock_client)

            mock_handle.assert_called_once_with("RT-AX88U", "RT-AX86U")

    def test_refresh_router_info_no_switch_same_product_id(self):
        """Test that no switch is detected when product_id remains the same."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        old_info = MagicMock(product_id="RT-AX88U")
        new_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = new_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._router_info = old_info
        exporter._previous_product_id = "RT-AX88U"

        with patch.object(exporter, "_handle_node_switch") as mock_handle:
            exporter._refresh_router_info(mock_client)

            mock_handle.assert_not_called()

    def test_refresh_router_info_no_switch_on_first_call(self):
        """Test that no switch is detected on first call (no previous product_id)."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        new_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = new_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._previous_product_id = None  # First call

        with patch.object(exporter, "_handle_node_switch") as mock_handle:
            exporter._refresh_router_info(mock_client)

            mock_handle.assert_not_called()

    def test_handle_node_switch_clears_all_metrics(self):
        """Test that node switch clears all collector metrics."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        with (
            patch.object(container, "clear_all_metrics") as mock_clear,
            patch.object(container, "reset_all_collector_state"),
            patch.object(exporter, "_clear_stale_product_id_labels"),
            patch("asus_router_exporter.server.exporter.SelfMetrics") as mock_metrics_cls,
        ):
            mock_metrics = MagicMock()
            mock_metrics_cls.get_instance.return_value = mock_metrics

            exporter._handle_node_switch("RT-AX88U", "RT-AX86U")

            mock_clear.assert_called_once()

    def test_handle_node_switch_resets_collector_state(self):
        """Test that node switch resets all collector internal state."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        with (
            patch.object(container, "clear_all_metrics"),
            patch.object(container, "reset_all_collector_state") as mock_reset,
            patch.object(exporter, "_clear_stale_product_id_labels"),
            patch("asus_router_exporter.server.exporter.SelfMetrics") as mock_metrics_cls,
        ):
            mock_metrics = MagicMock()
            mock_metrics_cls.get_instance.return_value = mock_metrics

            exporter._handle_node_switch("RT-AX88U", "RT-AX86U")

            mock_reset.assert_called_once()

    def test_handle_node_switch_clears_stale_labels(self):
        """Test that node switch clears stale product_id labels from exporter metrics."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        with (
            patch.object(container, "clear_all_metrics"),
            patch.object(container, "reset_all_collector_state"),
            patch.object(exporter, "_clear_stale_product_id_labels") as mock_clear_labels,
            patch("asus_router_exporter.server.exporter.SelfMetrics") as mock_metrics_cls,
        ):
            mock_metrics = MagicMock()
            mock_metrics_cls.get_instance.return_value = mock_metrics

            exporter._handle_node_switch("RT-AX88U", "RT-AX86U")

            mock_clear_labels.assert_called_once_with("RT-AX88U")

    def test_handle_node_switch_records_metric(self):
        """Test that node switch records a self-metric."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        with (
            patch.object(container, "clear_all_metrics"),
            patch.object(container, "reset_all_collector_state"),
            patch.object(exporter, "_clear_stale_product_id_labels"),
            patch("asus_router_exporter.server.exporter.SelfMetrics") as mock_metrics_cls,
        ):
            mock_metrics = MagicMock()
            mock_metrics_cls.get_instance.return_value = mock_metrics

            exporter._handle_node_switch("RT-AX88U", "RT-AX86U")

            mock_metrics.record_node_switch.assert_called_once_with("RT-AX88U", "RT-AX86U")

    def test_clear_stale_product_id_labels_removes_up_metric(self):
        """Test that stale product_id label is removed from up metric."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)
        # Set the metric with the old product_id
        exporter._up.labels(product_id="RT-AX88U").set(1)

        exporter._clear_stale_product_id_labels("RT-AX88U")

        # The label should be removed (accessing it would recreate it with default)
        assert ("RT-AX88U",) not in exporter._up._metrics

    def test_clear_stale_product_id_labels_removes_scrape_duration_metric(self):
        """Test that stale product_id label is removed from scrape_duration metric."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)
        # Set the metric with the old product_id
        exporter._scrape_duration.labels(product_id="RT-AX88U").set(0.5)

        exporter._clear_stale_product_id_labels("RT-AX88U")

        # The label should be removed
        assert ("RT-AX88U",) not in exporter._scrape_duration._metrics

    def test_clear_stale_product_id_labels_handles_nonexistent_label(self):
        """Test that clearing nonexistent label does not raise exception."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        # Should not raise exception
        exporter._clear_stale_product_id_labels("NONEXISTENT")

    def test_collect_router_info_sets_previous_product_id(self):
        """Test that initial router info collection sets previous_product_id."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        assert exporter._previous_product_id is None

        exporter._collect_router_info()

        assert exporter._previous_product_id == "RT-AX88U"

    def test_collect_router_info_sets_unknown_on_failure(self):
        """Test that failed initial router info collection sets previous_product_id to unknown."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_client.get_info.side_effect = Exception("Connection failed")
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._collect_router_info()

        assert exporter._previous_product_id == "unknown"

    def test_refresh_router_info_updates_previous_product_id(self):
        """Test that refresh updates previous_product_id."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock()
        new_info = MagicMock(product_id="RT-AX86U")
        mock_client.get_info.return_value = new_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._previous_product_id = "RT-AX88U"

        with patch.object(exporter, "_handle_node_switch"):
            exporter._refresh_router_info(mock_client)

        assert exporter._previous_product_id == "RT-AX86U"

    def test_node_switch_full_flow(self):
        """Integration test for complete node switch handling flow."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)
        container._initialized = True

        mock_client = MagicMock()
        old_info = MagicMock(product_id="RT-AX88U-Main")
        new_info = MagicMock(product_id="RT-AX86U-Repeater")
        mock_client.get_info.return_value = new_info
        container.set_router_client(mock_client)

        exporter = Exporter(container)
        exporter._router_info = old_info
        exporter._previous_product_id = "RT-AX88U-Main"
        # Set initial metric values
        exporter._up.labels(product_id="RT-AX88U-Main").set(1)
        exporter._scrape_duration.labels(product_id="RT-AX88U-Main").set(0.5)

        # Refresh should detect the switch and handle it
        with patch("asus_router_exporter.server.exporter.SelfMetrics") as mock_metrics_cls:
            mock_metrics = MagicMock()
            mock_metrics_cls.get_instance.return_value = mock_metrics

            exporter._refresh_router_info(mock_client)

            # Verify node switch was recorded
            mock_metrics.record_node_switch.assert_called_once_with("RT-AX88U-Main", "RT-AX86U-Repeater")

        # Verify stale labels were removed
        assert ("RT-AX88U-Main",) not in exporter._up._metrics
        assert ("RT-AX88U-Main",) not in exporter._scrape_duration._metrics

        # Verify router_info and previous_product_id were updated
        assert exporter._router_info is new_info
        assert exporter._previous_product_id == "RT-AX86U-Repeater"
