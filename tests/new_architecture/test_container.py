"""
Tests for the Container dependency injection module.
"""

import sys

sys.path.insert(0, "src")

from unittest.mock import MagicMock, patch

from prometheus_client import CollectorRegistry

from asus_router_exporter.core.config import Config
from asus_router_exporter.core.container import Container
from asus_router_exporter.core.protocols import RouterClientProtocol


class MockCollector:
    """Mock collector for testing."""

    name = "mock_collector"

    def __init__(self, registry=None, config=None):
        self.registry = registry
        self.config = config
        self.enabled = True
        self.collected = False
        self.cleared = False
        self.cleaned_up = False

    def collect(self, client, router_info):
        self.collected = True

    def _clear_metrics(self):
        self.cleared = True

    def clear_metrics(self):
        """Public interface for clearing metrics."""
        self._clear_metrics()

    def cleanup(self):
        self.cleaned_up = True


class MockCollectorDisabled(MockCollector):
    """Mock collector that is disabled."""

    name = "mock_collector_disabled"

    def __init__(self, registry=None, config=None):
        super().__init__(registry, config)
        self.enabled = False


class MockCollectorFailsOnCollect(MockCollector):
    """Mock collector that fails on collect."""

    name = "mock_collector_fails"

    def collect(self, client, router_info):
        raise RuntimeError("Collection failed")


class MockCollectorFailsOnClear(MockCollector):
    """Mock collector that fails on clear."""

    name = "mock_collector_fails_clear"

    def collect(self, client, router_info):
        raise RuntimeError("Collection failed")

    def _clear_metrics(self):
        raise RuntimeError("Clear failed")

    def clear_metrics(self):
        """Public interface - also fails."""
        self._clear_metrics()


class MockCollectorFailsOnInit(MockCollector):
    """
    Mock collector that fails on initialization.

    Note: This class intentionally does NOT call super().__init__().
    The purpose is to test error handling when a collector fails
    immediately during construction, before any parent initialization
    completes. This simulates real-world scenarios where a collector
    might fail due to missing dependencies or invalid configuration.
    """

    name = "mock_collector_fails_init"

    def __init__(self, registry=None, config=None):  # noqa: B027
        raise RuntimeError("Initialization failed")


class MockCollectorFailsOnCleanup(MockCollector):
    """Mock collector that fails on cleanup."""

    name = "mock_collector_fails_cleanup"

    def cleanup(self):
        raise RuntimeError("Cleanup failed")


class TestContainerInit:
    """Tests for Container initialization."""

    def test_init_with_config(self):
        config = Config.from_env()
        registry = CollectorRegistry()
        container = Container(config, registry)

        assert container.config is config
        assert container.registry is registry
        assert container._initialized is False
        assert container._collectors == []

    def test_init_with_default_registry(self):
        config = Config.from_env()
        container = Container(config)

        # Should use default REGISTRY
        assert container.registry is not None

    def test_from_config_loads_config(self):
        registry = CollectorRegistry()
        container = Container.from_config(None, registry)

        # Should have default config values
        assert container.config.get("exporter.port") == 8000

    def test_from_env_creates_container(self):
        registry = CollectorRegistry()
        container = Container.from_env(registry)

        assert container.config is not None
        assert container.registry is registry


class TestContainerProperties:
    """Tests for Container property access."""

    def test_config_property(self):
        config = Config.from_env()
        container = Container(config)

        assert container.config is config

    def test_registry_property(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        assert container.registry is registry

    def test_collectors_property_empty_before_init(self):
        config = Config.from_env()
        container = Container(config)

        assert container.collectors == []

    @patch("asus_router_exporter.core.container.CompositeErrorHandler")
    def test_error_handler_lazy_creation(self, mock_error_handler_cls):
        mock_handler = MagicMock()
        mock_error_handler_cls.from_config.return_value = mock_handler

        config = Config.from_env()
        container = Container(config)

        # Should not be created yet
        assert container._error_handler is None

        # Access property to trigger creation
        handler = container.error_handler

        assert handler is mock_handler
        mock_error_handler_cls.from_config.assert_called_once_with(config)

    @patch("asus_router_exporter.core.container.CompositeErrorHandler")
    def test_error_handler_cached(self, mock_error_handler_cls):
        mock_handler = MagicMock()
        mock_error_handler_cls.from_config.return_value = mock_handler

        config = Config.from_env()
        container = Container(config)

        # Access twice
        handler1 = container.error_handler
        handler2 = container.error_handler

        # Should be same instance
        assert handler1 is handler2
        # Should only create once
        mock_error_handler_cls.from_config.assert_called_once()


class TestContainerRouterClient:
    """Tests for router client management."""

    def test_set_router_client(self):
        config = Config.from_env()
        container = Container(config)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        assert container._router_client is mock_client
        assert container.router_client is mock_client

    @patch("asus_router_exporter.client.router_client.RouterClientFactory")
    def test_router_client_lazy_creation(self, mock_factory_cls):
        mock_client = MagicMock(spec=RouterClientProtocol)
        mock_factory = MagicMock()
        mock_factory.auth.return_value = mock_client
        mock_factory_cls.return_value = mock_factory

        config = Config({"router": {"host": "10.0.0.1", "auth": "admin:pass"}})
        container = Container(config)

        # Should not be created yet
        assert container._router_client is None

        # Access property to trigger creation
        client = container.router_client

        assert client is mock_client
        mock_factory_cls.assert_called_once_with("10.0.0.1")
        mock_factory.auth.assert_called_once_with("admin:pass")

    @patch("asus_router_exporter.client.router_client.RouterClientFactory")
    def test_router_client_cached(self, mock_factory_cls):
        mock_client = MagicMock(spec=RouterClientProtocol)
        mock_factory = MagicMock()
        mock_factory.auth.return_value = mock_client
        mock_factory_cls.return_value = mock_factory

        config = Config({"router": {"host": "10.0.0.1", "auth": "admin:pass"}})
        container = Container(config)

        # Access twice
        client1 = container.router_client
        client2 = container.router_client

        # Should be same instance
        assert client1 is client2
        mock_factory_cls.assert_called_once()


class TestContainerCollectorRegistration:
    """Tests for collector registration."""

    def test_register_single_collector(self):
        config = Config.from_env()
        container = Container(config)

        container.register_collector(MockCollector)

        assert MockCollector in container._collector_classes

    def test_register_collector_no_duplicates(self):
        config = Config.from_env()
        container = Container(config)

        container.register_collector(MockCollector)
        container.register_collector(MockCollector)  # Register again

        # Should only be registered once
        assert container._collector_classes.count(MockCollector) == 1

    def test_register_multiple_collectors(self):
        config = Config.from_env()
        container = Container(config)

        container.register_collectors(MockCollector, MockCollectorDisabled)

        assert MockCollector in container._collector_classes
        assert MockCollectorDisabled in container._collector_classes


class TestContainerInitialize:
    """Tests for container initialization."""

    def test_initialize_creates_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collector(MockCollector)
        container.initialize()

        assert len(container.collectors) == 1
        assert container._initialized is True
        collector = container.collectors[0]
        assert collector.registry is registry
        assert collector.config is config

    def test_initialize_multiple_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorDisabled)
        container.initialize()

        assert len(container.collectors) == 2

    def test_initialize_skips_on_error(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorFailsOnInit)
        container.initialize()

        # Only the successful one should be initialized
        assert len(container.collectors) == 1
        assert container.collectors[0].name == "mock_collector"

    def test_initialize_only_once(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collector(MockCollector)
        container.initialize()

        # Try to initialize again
        container.register_collector(MockCollectorDisabled)
        container.initialize()

        # Should still only have one collector (second init skipped)
        assert len(container.collectors) == 1


class TestContainerCollectMetrics:
    """Tests for metric collection."""

    def test_collect_metrics_calls_enabled_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collector(MockCollector)
        container.initialize()

        router_info = MagicMock()
        container.collect_metrics(router_info)

        assert container.collectors[0].collected is True

    def test_collect_metrics_skips_disabled_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collector(MockCollectorDisabled)
        container.initialize()

        router_info = MagicMock()
        container.collect_metrics(router_info)

        # Disabled collector should not be called
        assert container.collectors[0].collected is False

    def test_collect_metrics_clears_on_error(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collector(MockCollectorFailsOnCollect)
        container.initialize()

        router_info = MagicMock()
        container.collect_metrics(router_info)

        # Should have cleared metrics after error
        assert container.collectors[0].cleared is True

    def test_collect_metrics_handles_clear_error(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collector(MockCollectorFailsOnClear)
        container.initialize()

        router_info = MagicMock()
        # Should not raise even if clear fails
        container.collect_metrics(router_info)


class TestContainerClearMetrics:
    """Tests for clearing metrics."""

    def test_clear_all_metrics(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorDisabled)
        container.initialize()

        container.clear_all_metrics()

        # Both collectors should have been cleared
        assert container.collectors[0].cleared is True
        assert container.collectors[1].cleared is True

    def test_clear_all_metrics_handles_errors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorFailsOnClear)
        container.initialize()

        # Should not raise
        container.clear_all_metrics()

        # First one should still be cleared
        assert container.collectors[0].cleared is True


class TestContainerCleanup:
    """Tests for container cleanup."""

    def test_cleanup_cleans_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collector(MockCollector)
        container.initialize()

        assert len(container.collectors) == 1
        collector = container.collectors[0]

        container.cleanup()

        assert collector.cleaned_up is True
        assert container.collectors == []
        assert container._initialized is False

    def test_cleanup_handles_errors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorFailsOnCleanup)
        container.initialize()

        # Should not raise
        container.cleanup()

        # Both should be removed from list
        assert container.collectors == []


class TestContainerCollectorQueries:
    """Tests for collector query methods."""

    def test_get_enabled_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorDisabled)
        container.initialize()

        enabled = container.get_enabled_collectors()

        assert "mock_collector" in enabled
        assert "mock_collector_disabled" not in enabled

    def test_get_disabled_collectors(self):
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        container.register_collectors(MockCollector, MockCollectorDisabled)
        container.initialize()

        disabled = container.get_disabled_collectors()

        assert "mock_collector_disabled" in disabled
        assert "mock_collector" not in disabled

    def test_get_enabled_collectors_empty(self):
        config = Config.from_env()
        container = Container(config)

        # No collectors registered/initialized
        assert container.get_enabled_collectors() == []

    def test_get_disabled_collectors_empty(self):
        config = Config.from_env()
        container = Container(config)

        # No collectors registered/initialized
        assert container.get_disabled_collectors() == []


class TestContainerCacheClearing:
    """Tests for router client cache clearing behavior."""

    def test_collect_metrics_clears_cache_at_start(self):
        """Test that cache is cleared at the start of each collection cycle."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        mock_client.clear_cache = MagicMock()
        container.set_router_client(mock_client)

        container.register_collector(MockCollector)
        container.initialize()

        router_info = MagicMock()
        container.collect_metrics(router_info)

        # Cache is cleared once at the start of each collection cycle
        assert mock_client.clear_cache.call_count == 1

    def test_collect_metrics_clears_cache_before_collection(self):
        """Test that cache is cleared before any collector runs."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        mock_client.clear_cache = MagicMock()
        container.set_router_client(mock_client)

        container.register_collector(MockCollectorFailsOnCollect)
        container.initialize()

        router_info = MagicMock()
        container.collect_metrics(router_info)

        # Cache is cleared at start, regardless of collector success/failure
        assert mock_client.clear_cache.call_count == 1

    def test_collect_metrics_clears_cache_even_when_no_enabled_collectors(self):
        """Test that cache is cleared even when there are no enabled collectors."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        mock_client.clear_cache = MagicMock()
        container.set_router_client(mock_client)

        container.register_collector(MockCollectorDisabled)
        container.initialize()

        router_info = MagicMock()
        result = container.collect_metrics(router_info)

        # Should return True (nothing failed) and still clear cache
        assert result is True
        mock_client.clear_cache.assert_called_once()

    def test_collect_metrics_calls_clear_cache_via_protocol(self):
        """Test that collect_metrics calls clear_cache via the RouterClientProtocol."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        # Client that implements RouterClientProtocol
        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collector(MockCollector)
        container.initialize()

        router_info = MagicMock()
        result = container.collect_metrics(router_info)

        assert result is True
        # clear_cache is called once at start of cycle
        assert mock_client.clear_cache.call_count == 1

    def test_cache_cleared_each_cycle(self):
        """Test that cache is cleared at the start of each collection cycle."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        clear_call_count = []

        def track_clear():
            clear_call_count.append(1)

        mock_client.clear_cache = track_clear
        container.set_router_client(mock_client)

        container.register_collector(MockCollector)
        container.initialize()

        router_info = MagicMock()

        # Run multiple collection cycles
        container.collect_metrics(router_info)
        container.collect_metrics(router_info)
        container.collect_metrics(router_info)

        # Cache should be cleared once per cycle
        assert len(clear_call_count) == 3


class TestContainerIntegration:
    """Integration tests for Container."""

    def test_full_lifecycle(self):
        """Test full container lifecycle: create -> register -> init -> collect -> cleanup."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        # Set mock client
        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        # Register collectors
        container.register_collectors(MockCollector, MockCollectorDisabled)

        # Initialize
        container.initialize()
        assert len(container.collectors) == 2
        assert container._initialized is True

        # Collect metrics
        router_info = MagicMock()
        container.collect_metrics(router_info)

        # Check enabled collector was used
        enabled_collector = next(c for c in container.collectors if c.enabled)
        assert enabled_collector.collected is True

        # Cleanup
        container.cleanup()
        assert container.collectors == []
        assert container._initialized is False
