"""
Tests for the Exporter module.
"""

import sys

sys.path.insert(0, 'src')

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
        info = FallbackRouterInfo(
            product_id="RT-AX88U",
            lan_hwaddr="AA:BB:CC:DD:EE:FF"
        )

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
        assert exporter._running is False

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

        with patch.object(container, '_error_handler', mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(exporter, '_collect_metrics'):
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

        with patch.object(container, '_error_handler', mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(container, 'clear_all_metrics'):
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

        with patch.object(container, '_error_handler', mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(container, 'clear_all_metrics') as mock_clear:
                exporter._collect_with_error_handling()
                mock_clear.assert_called_once()

    def test_scrape_duration_recorded(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_error_handler = MagicMock()
        mock_error_handler.execute = MagicMock(side_effect=lambda fn: fn())

        with patch.object(container, '_error_handler', mock_error_handler):
            exporter = Exporter(container)
            exporter._router_info = MagicMock(product_id="RT-AX88U")
            exporter._container._error_handler = mock_error_handler

            with patch.object(exporter, '_collect_metrics'):
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

        exporter = Exporter(container)
        mock_router_info = MagicMock()
        exporter._router_info = mock_router_info

        with patch.object(container, 'collect_metrics') as mock_collect:
            exporter._collect_metrics()
            mock_collect.assert_called_once_with(mock_router_info)


class TestExporterShutdown:
    """Tests for shutdown handling."""

    def test_handle_shutdown_sets_running_false(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)
        exporter._running = True

        exporter._handle_shutdown(signal.SIGINT, None)

        assert exporter._running is False

    def test_shutdown_cleans_up_container(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        exporter = Exporter(container)

        with patch.object(container, 'cleanup') as mock_cleanup:
            exporter._shutdown()
            mock_cleanup.assert_called_once()


class TestExporterRun:
    """Tests for the run method."""

    @patch('asus_router_exporter.server.exporter.start_http_server')
    @patch('asus_router_exporter.server.exporter.time.sleep')
    @patch('asus_router_exporter.server.exporter.signal.signal')
    def test_run_starts_http_server(self, mock_signal, mock_sleep, mock_start_server):
        registry = CollectorRegistry()
        config = Config({'exporter': {'port': 9100, 'scrape_interval': 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Make sleep raise KeyboardInterrupt to stop the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        exporter = Exporter(container)

        with patch.object(container, 'cleanup'):
            try:
                exporter.run()
            except KeyboardInterrupt:
                pass

        mock_start_server.assert_called_once_with(9100, registry=registry)

    @patch('asus_router_exporter.server.exporter.start_http_server')
    @patch('asus_router_exporter.server.exporter.time.sleep')
    @patch('asus_router_exporter.server.exporter.signal.signal')
    def test_run_registers_signal_handlers(self, mock_signal, mock_sleep, mock_start_server):
        registry = CollectorRegistry()
        config = Config({'exporter': {'port': 8000, 'scrape_interval': 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Make sleep raise KeyboardInterrupt to stop the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        exporter = Exporter(container)

        with patch.object(container, 'cleanup'):
            try:
                exporter.run()
            except KeyboardInterrupt:
                pass

        # Check SIGINT and SIGTERM handlers were registered
        signal_calls = [call[0][0] for call in mock_signal.call_args_list]
        assert signal.SIGINT in signal_calls
        assert signal.SIGTERM in signal_calls

    @patch('asus_router_exporter.server.exporter.start_http_server')
    @patch('asus_router_exporter.server.exporter.time.sleep')
    @patch('asus_router_exporter.server.exporter.signal.signal')
    def test_run_collects_router_info(self, mock_signal, mock_sleep, mock_start_server):
        registry = CollectorRegistry()
        config = Config({'exporter': {'port': 8000, 'scrape_interval': 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Make sleep raise KeyboardInterrupt to stop the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        exporter = Exporter(container)

        with patch.object(container, 'cleanup'):
            try:
                exporter.run()
            except KeyboardInterrupt:
                pass

        # Router info should have been collected
        mock_client.get_info.assert_called_once()

    @patch('asus_router_exporter.server.exporter.start_http_server')
    @patch('asus_router_exporter.server.exporter.time.sleep')
    @patch('asus_router_exporter.server.exporter.signal.signal')
    def test_run_cleanup_on_exit(self, mock_signal, mock_sleep, mock_start_server):
        registry = CollectorRegistry()
        config = Config({'exporter': {'port': 8000, 'scrape_interval': 30}})
        container = Container(config, registry)

        mock_client = MagicMock()
        mock_info = MagicMock(product_id="RT-AX88U")
        mock_client.get_info.return_value = mock_info
        container.set_router_client(mock_client)

        # Make sleep raise KeyboardInterrupt to stop the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        exporter = Exporter(container)

        with patch.object(container, 'cleanup') as mock_cleanup:
            try:
                exporter.run()
            except KeyboardInterrupt:
                pass

            mock_cleanup.assert_called_once()


class TestCreateExporter:
    """Tests for create_exporter factory function."""

    @patch('asus_router_exporter.server.exporter.Container')
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

    @patch('asus_router_exporter.server.exporter.Container')
    def test_create_exporter_from_config(self, mock_container_cls):
        mock_container = MagicMock()
        mock_container.config = Config.from_env()
        mock_container.registry = CollectorRegistry()
        mock_container_cls.from_config.return_value = mock_container

        exporter = create_exporter(config_path="config.yaml")

        mock_container_cls.from_config.assert_called_once_with("config.yaml")
        assert isinstance(exporter, Exporter)

    @patch('asus_router_exporter.server.exporter.Container')
    def test_create_exporter_with_overrides(self, mock_container_cls):
        mock_config = MagicMock()
        mock_container = MagicMock()
        mock_container.config = mock_config
        mock_container.registry = CollectorRegistry()
        mock_container_cls.from_env.return_value = mock_container

        # The exporter is created to verify the function runs and applies overrides
        create_exporter(
            router_host="10.0.0.1",
            router_auth="admin:pass",
            metrics_port=9100
        )

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
        with patch.object(container, 'collect_metrics') as mock_collect:
            exporter._collect_metrics()
            mock_collect.assert_called_once_with(mock_info)
