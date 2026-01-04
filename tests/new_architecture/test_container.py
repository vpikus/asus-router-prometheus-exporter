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

    @patch("asus_router_exporter.client.RouterClientFactory")
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
        mock_factory_cls.assert_called_once_with("10.0.0.1", reauth_interval=1800)
        mock_factory.auth.assert_called_once_with("admin:pass")

    @patch("asus_router_exporter.client.RouterClientFactory")
    def test_router_client_with_custom_reauth_interval(self, mock_factory_cls):
        """Test that custom reauth_interval is passed to factory."""
        mock_client = MagicMock(spec=RouterClientProtocol)
        mock_factory = MagicMock()
        mock_factory.auth.return_value = mock_client
        mock_factory_cls.return_value = mock_factory

        config = Config({"router": {"host": "10.0.0.1", "auth": "admin:pass", "reauth_interval": 3600}})
        container = Container(config)

        # Access property to trigger creation
        _ = container.router_client

        mock_factory_cls.assert_called_once_with("10.0.0.1", reauth_interval=3600)

    @patch("asus_router_exporter.client.RouterClientFactory")
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


class MockCollectorConnectionError(MockCollector):
    """Mock collector that raises a connection error."""

    name = "mock_collector_connection_error"

    def collect(self, client, router_info):
        from requests.exceptions import ConnectionError as RequestsConnectionError

        raise RequestsConnectionError("Connection refused")


class MockCollectorOSError(MockCollector):
    """Mock collector that raises an OSError with ECONNREFUSED."""

    name = "mock_collector_oserror"

    def collect(self, client, router_info):
        import errno

        err = OSError("Connection refused")
        err.errno = errno.ECONNREFUSED
        raise err


class TestContainerConnectionErrorHandling:
    """Tests for connection error short-circuit behavior."""

    def test_collect_metrics_short_circuits_on_connection_error(self):
        """Test that remaining collectors are skipped when connection error occurs."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        # Register connection error collector first, then a normal one
        container.register_collectors(MockCollectorConnectionError, MockCollector)
        container.initialize()

        router_info = MagicMock()

        # Should raise RouterConnectionError wrapping the original error
        import pytest
        from requests.exceptions import ConnectionError as RequestsConnectionError

        from asus_router_exporter.core.exceptions import RouterConnectionError

        with pytest.raises(RouterConnectionError) as exc_info:
            container.collect_metrics(router_info)

        # Verify the original exception is preserved as __cause__
        assert isinstance(exc_info.value.__cause__, RequestsConnectionError)
        # Verify recoverable=False for retry skipping
        assert exc_info.value.recoverable is False
        # First collector raised error, second should NOT have been called
        assert container.collectors[1].collected is False

    def test_collect_metrics_reraises_connection_error(self):
        """Test that connection errors are wrapped in RouterConnectionError."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collector(MockCollectorConnectionError)
        container.initialize()

        router_info = MagicMock()

        import pytest
        from requests.exceptions import ConnectionError as RequestsConnectionError

        from asus_router_exporter.core.exceptions import RouterConnectionError

        with pytest.raises(RouterConnectionError) as exc_info:
            container.collect_metrics(router_info)

        # Original exception preserved as __cause__
        assert isinstance(exc_info.value.__cause__, RequestsConnectionError)
        assert exc_info.value.recoverable is False

    def test_collect_metrics_short_circuits_on_oserror(self):
        """Test that OSError with connection-related errno triggers short-circuit."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        container.register_collectors(MockCollectorOSError, MockCollector)
        container.initialize()

        router_info = MagicMock()

        import pytest

        from asus_router_exporter.core.exceptions import RouterConnectionError

        with pytest.raises(RouterConnectionError) as exc_info:
            container.collect_metrics(router_info)

        # Original OSError preserved as __cause__
        assert isinstance(exc_info.value.__cause__, OSError)
        assert exc_info.value.recoverable is False
        # Second collector should NOT have been called
        assert container.collectors[1].collected is False

    def test_collect_metrics_does_not_short_circuit_on_regular_error(self):
        """Test that regular errors don't trigger short-circuit."""
        registry = CollectorRegistry()
        config = Config.from_env()
        container = Container(config, registry)

        mock_client = MagicMock(spec=RouterClientProtocol)
        container.set_router_client(mock_client)

        # Regular error collector first, then a normal one
        container.register_collectors(MockCollectorFailsOnCollect, MockCollector)
        container.initialize()

        router_info = MagicMock()
        result = container.collect_metrics(router_info)

        # Should return True (second collector succeeded)
        assert result is True
        # Second collector SHOULD have been called despite first failing
        assert container.collectors[1].collected is True


class TestIsConnectionError:
    """Tests for _is_connection_error helper method."""

    def test_detects_requests_connection_error(self):
        """Test detection of requests.ConnectionError."""
        from requests.exceptions import ConnectionError as RequestsConnectionError

        config = Config.from_env()
        container = Container(config)

        error = RequestsConnectionError("Connection refused")
        assert container._is_connection_error(error) is True

    def test_detects_builtin_connection_error(self):
        """Test detection of built-in ConnectionError."""
        config = Config.from_env()
        container = Container(config)

        error = ConnectionError("Connection refused")
        assert container._is_connection_error(error) is True

    def test_detects_oserror_with_econnrefused(self):
        """Test detection of OSError with ECONNREFUSED errno."""
        import errno

        config = Config.from_env()
        container = Container(config)

        error = OSError("Connection refused")
        error.errno = errno.ECONNREFUSED
        assert container._is_connection_error(error) is True

    def test_detects_oserror_with_etimedout(self):
        """Test detection of OSError with ETIMEDOUT errno."""
        import errno

        config = Config.from_env()
        container = Container(config)

        error = OSError("Connection timed out")
        error.errno = errno.ETIMEDOUT
        assert container._is_connection_error(error) is True

    def test_detects_oserror_with_econnaborted(self):
        """Test detection of OSError with ECONNABORTED errno."""
        import errno

        config = Config.from_env()
        container = Container(config)

        error = OSError("Connection aborted")
        error.errno = errno.ECONNABORTED
        assert container._is_connection_error(error) is True

    def test_detects_oserror_with_econnreset(self):
        """Test detection of OSError with ECONNRESET errno."""
        import errno

        config = Config.from_env()
        container = Container(config)

        error = OSError("Connection reset by peer")
        error.errno = errno.ECONNRESET
        assert container._is_connection_error(error) is True

    def test_ignores_oserror_with_other_errno(self):
        """Test that OSError with unrelated errno is not treated as connection error."""
        import errno

        config = Config.from_env()
        container = Container(config)

        error = OSError("Permission denied")
        error.errno = errno.EACCES
        assert container._is_connection_error(error) is False

    def test_detects_chained_connection_error_via_cause(self):
        """Test detection of connection error in explicit exception chain (__cause__)."""
        from requests.exceptions import ConnectionError as RequestsConnectionError

        config = Config.from_env()
        container = Container(config)

        # Create an explicitly chained exception (raise X from Y)
        inner = RequestsConnectionError("Connection refused")
        outer = RuntimeError("Collection failed")
        outer.__cause__ = inner

        assert container._is_connection_error(outer) is True

    def test_detects_chained_connection_error_via_context(self):
        """Test detection of connection error in implicit exception chain (__context__)."""
        from requests.exceptions import ConnectionError as RequestsConnectionError

        config = Config.from_env()
        container = Container(config)

        # Create an implicitly chained exception (exception during handling)
        inner = RequestsConnectionError("Connection refused")
        outer = RuntimeError("Handler failed")
        outer.__context__ = inner

        assert container._is_connection_error(outer) is True

    def test_ignores_regular_runtime_error(self):
        """Test that regular RuntimeError is not treated as connection error."""
        config = Config.from_env()
        container = Container(config)

        error = RuntimeError("Something went wrong")
        assert container._is_connection_error(error) is False

    def test_explores_both_cause_and_context_branches(self):
        """Test that both __cause__ and __context__ branches are explored."""
        from requests.exceptions import ConnectionError as RequestsConnectionError

        config = Config.from_env()
        container = Container(config)

        # Create exception with both __cause__ and __context__ pointing to different exceptions
        # The ConnectionError is only reachable via __context__, not __cause__
        outer = RuntimeError("Outer error")
        cause_branch = ValueError("Not a connection error")
        context_branch = RequestsConnectionError("Connection refused")
        outer.__cause__ = cause_branch
        outer.__context__ = context_branch

        # Should find ConnectionError in the __context__ branch
        assert container._is_connection_error(outer) is True

    def test_handles_cyclic_exception_chain(self):
        """Test that cyclic exception chains don't cause infinite loops."""
        config = Config.from_env()
        container = Container(config)

        # Create a cyclic exception chain (malformed, but should not hang)
        e1 = RuntimeError("Error 1")
        e2 = RuntimeError("Error 2")
        e1.__cause__ = e2
        e2.__cause__ = e1  # Creates cycle

        # Should return False without hanging
        assert container._is_connection_error(e1) is False


class TestContainerResetAllCollectorState:
    """Tests for Container.reset_all_collector_state method."""

    def test_reset_all_collector_state_calls_reset_on_all_collectors(self):
        """Test that reset_all_collector_state calls reset_state on all collectors."""
        config = Config.from_env()
        container = Container(config)

        mock_collector1 = MagicMock()
        mock_collector1.name = "collector1"
        mock_collector2 = MagicMock()
        mock_collector2.name = "collector2"
        container._collectors = [mock_collector1, mock_collector2]

        container.reset_all_collector_state()

        mock_collector1.reset_state.assert_called_once()
        mock_collector2.reset_state.assert_called_once()

    def test_reset_all_collector_state_handles_exceptions(self):
        """Test that reset_all_collector_state continues on exception."""
        config = Config.from_env()
        container = Container(config)

        mock_collector1 = MagicMock()
        mock_collector1.name = "collector1"
        mock_collector1.reset_state.side_effect = RuntimeError("Reset failed")

        mock_collector2 = MagicMock()
        mock_collector2.name = "collector2"

        container._collectors = [mock_collector1, mock_collector2]

        # Should not raise, and should continue to second collector
        container.reset_all_collector_state()

        mock_collector1.reset_state.assert_called_once()
        mock_collector2.reset_state.assert_called_once()

    def test_reset_all_collector_state_empty_collectors(self):
        """Test that reset_all_collector_state handles empty collectors list."""
        config = Config.from_env()
        container = Container(config)
        container._collectors = []

        # Should not raise
        container.reset_all_collector_state()
