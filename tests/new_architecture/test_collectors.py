"""
Tests for the collector modules.
"""

import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, "src")

from prometheus_client import CollectorRegistry

from asus_router_exporter.collectors.base import BaseCollector, LabeledMetricsMixin
from asus_router_exporter.collectors.cpu import CPUCollector
from asus_router_exporter.core.exceptions import CollectorError


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


class TestBaseCollector:
    """Tests for BaseCollector abstract class."""

    def test_collector_initialization_enabled(self):
        config = MockConfig({"collectors": {"test": {"enabled": True}}})
        registry = CollectorRegistry()

        class TestCollector(BaseCollector):
            name = "test"

            def _create_metrics(self):
                pass

            def _collect_metrics(self, router_client, router_info):
                pass

        collector = TestCollector(registry, config)
        assert collector.enabled is True

    def test_collector_initialization_disabled(self):
        config = MockConfig({"collectors": {"test": {"enabled": False}}})
        registry = CollectorRegistry()

        class TestCollector(BaseCollector):
            name = "test"

            def _create_metrics(self):
                self.metrics_created = True

            def _collect_metrics(self, router_client, router_info):
                pass

        collector = TestCollector(registry, config)
        assert collector.enabled is False
        assert not hasattr(collector, "metrics_created")

    def test_collect_disabled_collector(self):
        config = MockConfig({"collectors": {"test": {"enabled": False}}})
        registry = CollectorRegistry()

        class TestCollector(BaseCollector):
            name = "test"
            collect_called = False

            def _create_metrics(self):
                pass

            def _collect_metrics(self, router_client, router_info):
                self.collect_called = True

        collector = TestCollector(registry, config)
        collector.collect(Mock(), Mock())

        assert collector.collect_called is False

    def test_collect_raises_collector_error(self):
        config = MockConfig({"collectors": {"test": {"enabled": True}}})
        registry = CollectorRegistry()

        class TestCollector(BaseCollector):
            name = "test"

            def _create_metrics(self):
                pass

            def _collect_metrics(self, router_client, router_info):
                raise ValueError("Test error")

        collector = TestCollector(registry, config)

        with pytest.raises(CollectorError) as exc_info:
            collector.collect(Mock(), Mock())

        assert "test" in str(exc_info.value)
        assert "Test error" in str(exc_info.value)

    def test_get_config(self):
        config = MockConfig({"collectors": {"test": {"enabled": True, "custom_option": "value"}}})
        registry = CollectorRegistry()

        class TestCollector(BaseCollector):
            name = "test"

            def _create_metrics(self):
                pass

            def _collect_metrics(self, router_client, router_info):
                pass

        collector = TestCollector(registry, config)
        assert collector.get_config("custom_option") == "value"
        assert collector.get_config("nonexistent", "default") == "default"


class TestLabeledMetricsMixin:
    """Tests for LabeledMetricsMixin."""

    def test_track_labels(self):
        mixin = LabeledMetricsMixin()
        mixin.__init__()

        mixin._track_labels("metric1", ("label1", "label2"))
        mixin._track_labels("metric1", ("label3", "label4"))

        assert ("label1", "label2") in mixin._active_labels["metric1"]
        assert ("label3", "label4") in mixin._active_labels["metric1"]

    def test_get_stale_labels(self):
        mixin = LabeledMetricsMixin()
        mixin.__init__()

        # Track initial labels
        mixin._track_labels("metric1", ("a", "b"))
        mixin._track_labels("metric1", ("c", "d"))

        # New current labels (missing 'a', 'b')
        current = {("c", "d"), ("e", "f")}
        stale = mixin._get_stale_labels("metric1", current)

        assert stale == {("a", "b")}

    def test_update_active_labels(self):
        mixin = LabeledMetricsMixin()
        mixin.__init__()

        mixin._track_labels("metric1", ("old",))
        mixin._update_active_labels("metric1", {("new",)})

        assert mixin._active_labels["metric1"] == {("new",)}


class TestCPUCollector:
    """Tests for CPUCollector."""

    def setup_method(self):
        self.registry = CollectorRegistry()
        self.config = MockConfig({"collectors": {"cpu": {"enabled": True}}})

    def test_cpu_collector_initialization(self):
        collector = CPUCollector(self.registry, self.config)

        assert collector.name == "cpu"
        assert collector.enabled is True
        assert len(collector._metrics) == 4  # temp, usage, total, percent

    def test_collect_temperature(self):
        collector = CPUCollector(self.registry, self.config)

        # Mock router client
        router_client = Mock()
        temp_info = Mock(cpu=65.5)
        router_client.get_core_temp.return_value = temp_info
        router_client.get_cpu_usage.return_value = []

        # Mock router info
        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Check temperature metric was set
        samples = list(collector._temperature.collect())
        assert len(samples) > 0

    def test_collect_cpu_usage_first_sample(self):
        collector = CPUCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_core_temp.return_value = Mock(cpu=50.0)

        cpu_info = Mock(usage=1000, total=10000)
        router_client.get_cpu_usage.return_value = [cpu_info]

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # First sample should set NaN for percentage (no delta available)
        # Uses composite key with product_id:cpu_id
        assert "RT-AX88U:0" in collector._previous_samples
        assert collector._previous_samples["RT-AX88U:0"]["usage"] == 1000
        assert collector._previous_samples["RT-AX88U:0"]["total"] == 10000

    def test_collect_cpu_usage_with_delta(self):
        collector = CPUCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_core_temp.return_value = Mock(cpu=50.0)

        # First sample
        cpu_info1 = Mock(usage=1000, total=10000)
        router_client.get_cpu_usage.return_value = [cpu_info1]
        router_info = Mock(product_id="RT-AX88U")
        collector.collect(router_client, router_info)

        # Second sample (50% usage: delta_usage=500, delta_total=1000)
        cpu_info2 = Mock(usage=1500, total=11000)
        router_client.get_cpu_usage.return_value = [cpu_info2]
        collector.collect(router_client, router_info)

        # Verify samples were stored (uses composite key with product_id:cpu_id)
        assert collector._previous_samples["RT-AX88U:0"]["usage"] == 1500
        assert collector._previous_samples["RT-AX88U:0"]["total"] == 11000

    def test_cleanup_clears_state(self):
        collector = CPUCollector(self.registry, self.config)
        collector._previous_samples = {"0": {"usage": 100, "total": 1000}}

        collector.cleanup()

        assert collector._previous_samples == {}

    def test_calculate_delta_normal(self):
        assert CPUCollector._calculate_delta(100, 50) == 50

    def test_calculate_delta_wrap_around(self):
        # When counter wraps (current < previous), return 0 to skip sample
        assert CPUCollector._calculate_delta(50, 100) == 0

    def test_disabled_collector(self):
        config = MockConfig({"collectors": {"cpu": {"enabled": False}}})
        collector = CPUCollector(self.registry, config)

        assert collector.enabled is False
        assert len(collector._metrics) == 0

    def test_temperature_collection_failure(self):
        collector = CPUCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_core_temp.side_effect = Exception("Connection failed")
        router_client.get_cpu_usage.return_value = []

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise - just logs warning
        collector.collect(router_client, router_info)

    def test_usage_collection_failure(self):
        collector = CPUCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_core_temp.return_value = Mock(cpu=50.0)
        router_client.get_cpu_usage.side_effect = Exception("Connection failed")

        router_info = Mock(product_id="RT-AX88U")

        # Should not raise - just logs warning
        collector.collect(router_client, router_info)

    def test_multiple_cpus(self):
        collector = CPUCollector(self.registry, self.config)

        router_client = Mock()
        router_client.get_core_temp.return_value = Mock(cpu=50.0)

        # Two CPUs
        cpu_infos = [Mock(usage=1000, total=10000), Mock(usage=2000, total=10000)]
        router_client.get_cpu_usage.return_value = cpu_infos

        router_info = Mock(product_id="RT-AX88U")

        collector.collect(router_client, router_info)

        # Uses composite key with product_id:cpu_id
        assert "RT-AX88U:0" in collector._previous_samples
        assert "RT-AX88U:1" in collector._previous_samples
