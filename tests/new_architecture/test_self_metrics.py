"""Tests for self-metrics module."""

from __future__ import annotations

import time

import pytest
from prometheus_client import CollectorRegistry

from asus_router_exporter.metrics.self_metrics import (
    CircuitBreakerStateValue,
    SelfMetrics,
)


class TestSelfMetrics:
    """Tests for SelfMetrics singleton."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        SelfMetrics.reset_instance()
        self.registry = CollectorRegistry()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        SelfMetrics.reset_instance()

    def test_singleton_pattern(self) -> None:
        """Test that get_instance returns the same instance."""
        instance1 = SelfMetrics.get_instance(self.registry)
        instance2 = SelfMetrics.get_instance()
        assert instance1 is instance2

    def test_reset_instance(self) -> None:
        """Test that reset_instance creates a new instance."""
        instance1 = SelfMetrics.get_instance(self.registry)
        SelfMetrics.reset_instance()
        # Need a new registry to avoid duplicate metric registration
        new_registry = CollectorRegistry()
        instance2 = SelfMetrics.get_instance(new_registry)
        assert instance1 is not instance2


class TestCircuitBreakerMetrics:
    """Tests for circuit breaker metrics."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        SelfMetrics.reset_instance()
        self.registry = CollectorRegistry()
        self.metrics = SelfMetrics.get_instance(self.registry)

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        SelfMetrics.reset_instance()

    def test_set_circuit_breaker_state_closed(self) -> None:
        """Test setting circuit breaker state to closed."""
        self.metrics.set_circuit_breaker_state(CircuitBreakerStateValue.CLOSED)
        value = self.registry.get_sample_value("asus_router_exporter_circuit_breaker_state")
        assert value == 0

    def test_set_circuit_breaker_state_open(self) -> None:
        """Test setting circuit breaker state to open."""
        self.metrics.set_circuit_breaker_state(CircuitBreakerStateValue.OPEN)
        value = self.registry.get_sample_value("asus_router_exporter_circuit_breaker_state")
        assert value == 1

    def test_set_circuit_breaker_state_half_open(self) -> None:
        """Test setting circuit breaker state to half-open."""
        self.metrics.set_circuit_breaker_state(CircuitBreakerStateValue.HALF_OPEN)
        value = self.registry.get_sample_value("asus_router_exporter_circuit_breaker_state")
        assert value == 2

    def test_set_circuit_breaker_failure_count(self) -> None:
        """Test setting circuit breaker failure count."""
        self.metrics.set_circuit_breaker_failure_count(5)
        value = self.registry.get_sample_value("asus_router_exporter_circuit_breaker_failure_count")
        assert value == 5

    def test_record_circuit_breaker_transition(self) -> None:
        """Test recording circuit breaker state transitions."""
        self.metrics.record_circuit_breaker_transition("closed", "open")
        self.metrics.record_circuit_breaker_transition("open", "half_open")
        self.metrics.record_circuit_breaker_transition("half_open", "closed")

        closed_to_open = self.registry.get_sample_value(
            "asus_router_exporter_circuit_breaker_state_transitions_total",
            {"from_state": "closed", "to_state": "open"},
        )
        open_to_half_open = self.registry.get_sample_value(
            "asus_router_exporter_circuit_breaker_state_transitions_total",
            {"from_state": "open", "to_state": "half_open"},
        )
        half_open_to_closed = self.registry.get_sample_value(
            "asus_router_exporter_circuit_breaker_state_transitions_total",
            {"from_state": "half_open", "to_state": "closed"},
        )

        assert closed_to_open == 1
        assert open_to_half_open == 1
        assert half_open_to_closed == 1


class TestRetryMetrics:
    """Tests for retry metrics."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        SelfMetrics.reset_instance()
        self.registry = CollectorRegistry()
        self.metrics = SelfMetrics.get_instance(self.registry)

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        SelfMetrics.reset_instance()

    def test_record_retry_attempt(self) -> None:
        """Test recording retry attempts."""
        self.metrics.record_retry_attempt()
        self.metrics.record_retry_attempt()
        self.metrics.record_retry_attempt()

        value = self.registry.get_sample_value("asus_router_exporter_retry_attempts_total")
        assert value == 3

    def test_record_retries_exhausted(self) -> None:
        """Test recording retries exhausted."""
        self.metrics.record_retries_exhausted()
        self.metrics.record_retries_exhausted()

        value = self.registry.get_sample_value("asus_router_exporter_retries_exhausted_total")
        assert value == 2


class TestCacheMetrics:
    """Tests for cache metrics."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        SelfMetrics.reset_instance()
        self.registry = CollectorRegistry()
        self.metrics = SelfMetrics.get_instance(self.registry)

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        SelfMetrics.reset_instance()

    def test_record_cache_hit(self) -> None:
        """Test recording cache hits."""
        self.metrics.record_cache_hit("uptime")
        self.metrics.record_cache_hit("uptime")
        self.metrics.record_cache_hit("sw_mode")

        uptime_hits = self.registry.get_sample_value(
            "asus_router_exporter_cache_hits_total",
            {"cache_key": "uptime"},
        )
        sw_mode_hits = self.registry.get_sample_value(
            "asus_router_exporter_cache_hits_total",
            {"cache_key": "sw_mode"},
        )

        assert uptime_hits == 2
        assert sw_mode_hits == 1

    def test_record_cache_miss(self) -> None:
        """Test recording cache misses."""
        self.metrics.record_cache_miss("uptime")
        self.metrics.record_cache_miss("supported_features")

        uptime_misses = self.registry.get_sample_value(
            "asus_router_exporter_cache_misses_total",
            {"cache_key": "uptime"},
        )
        features_misses = self.registry.get_sample_value(
            "asus_router_exporter_cache_misses_total",
            {"cache_key": "supported_features"},
        )

        assert uptime_misses == 1
        assert features_misses == 1


class TestCollectorMetrics:
    """Tests for collector metrics."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        SelfMetrics.reset_instance()
        self.registry = CollectorRegistry()
        self.metrics = SelfMetrics.get_instance(self.registry)

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        SelfMetrics.reset_instance()

    def test_record_collector_success(self) -> None:
        """Test recording collector successes."""
        self.metrics.record_collector_success("cpu")
        self.metrics.record_collector_success("cpu")
        self.metrics.record_collector_success("memory")

        cpu_success = self.registry.get_sample_value(
            "asus_router_exporter_collector_success_total",
            {"collector": "cpu"},
        )
        memory_success = self.registry.get_sample_value(
            "asus_router_exporter_collector_success_total",
            {"collector": "memory"},
        )

        assert cpu_success == 2
        assert memory_success == 1

    def test_record_collector_error(self) -> None:
        """Test recording collector errors."""
        self.metrics.record_collector_error("wireless")
        self.metrics.record_collector_error("clients")
        self.metrics.record_collector_error("clients")

        wireless_errors = self.registry.get_sample_value(
            "asus_router_exporter_collector_errors_total",
            {"collector": "wireless"},
        )
        clients_errors = self.registry.get_sample_value(
            "asus_router_exporter_collector_errors_total",
            {"collector": "clients"},
        )

        assert wireless_errors == 1
        assert clients_errors == 2

    def test_set_collector_duration(self) -> None:
        """Test setting collector duration."""
        self.metrics.set_collector_duration("cpu", 0.5)
        self.metrics.set_collector_duration("memory", 0.25)

        cpu_duration = self.registry.get_sample_value(
            "asus_router_exporter_collector_duration_seconds",
            {"collector": "cpu"},
        )
        memory_duration = self.registry.get_sample_value(
            "asus_router_exporter_collector_duration_seconds",
            {"collector": "memory"},
        )

        assert cpu_duration == 0.5
        assert memory_duration == 0.25

    def test_collector_duration_updates(self) -> None:
        """Test that collector duration can be updated (gauge behavior)."""
        self.metrics.set_collector_duration("cpu", 0.5)
        self.metrics.set_collector_duration("cpu", 0.75)

        cpu_duration = self.registry.get_sample_value(
            "asus_router_exporter_collector_duration_seconds",
            {"collector": "cpu"},
        )

        assert cpu_duration == 0.75


class TestApiMetrics:
    """Tests for API performance metrics."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        SelfMetrics.reset_instance()
        self.registry = CollectorRegistry()
        self.metrics = SelfMetrics.get_instance(self.registry)

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        SelfMetrics.reset_instance()

    def test_record_api_request(self) -> None:
        """Test recording API requests."""
        self.metrics.record_api_request("get_cpu_usage", 0.1)
        self.metrics.record_api_request("get_cpu_usage", 0.2)
        self.metrics.record_api_request("get_memory_usage", 0.15)

        cpu_count = self.registry.get_sample_value(
            "asus_router_exporter_api_requests_total",
            {"method": "get_cpu_usage"},
        )
        memory_count = self.registry.get_sample_value(
            "asus_router_exporter_api_requests_total",
            {"method": "get_memory_usage"},
        )

        assert cpu_count == 2
        assert memory_count == 1

    def test_record_api_request_histogram(self) -> None:
        """Test that API request duration is recorded in histogram."""
        self.metrics.record_api_request("get_netdev", 0.05)

        # Check histogram count
        count = self.registry.get_sample_value(
            "asus_router_exporter_api_request_duration_seconds_count",
            {"method": "get_netdev"},
        )
        assert count == 1

        # Check histogram sum
        total = self.registry.get_sample_value(
            "asus_router_exporter_api_request_duration_seconds_sum",
            {"method": "get_netdev"},
        )
        assert total == pytest.approx(0.05, abs=0.001)

    def test_record_api_error(self) -> None:
        """Test recording API errors."""
        self.metrics.record_api_error("get_clients")
        self.metrics.record_api_error("get_clients")
        self.metrics.record_api_error("get_info")

        clients_errors = self.registry.get_sample_value(
            "asus_router_exporter_api_errors_total",
            {"method": "get_clients"},
        )
        info_errors = self.registry.get_sample_value(
            "asus_router_exporter_api_errors_total",
            {"method": "get_info"},
        )

        assert clients_errors == 2
        assert info_errors == 1

    def test_track_api_call_context_manager_success(self) -> None:
        """Test track_api_call context manager on success."""
        with self.metrics.track_api_call("get_wireless_info"):
            time.sleep(0.01)  # Simulate work

        count = self.registry.get_sample_value(
            "asus_router_exporter_api_requests_total",
            {"method": "get_wireless_info"},
        )
        duration_count = self.registry.get_sample_value(
            "asus_router_exporter_api_request_duration_seconds_count",
            {"method": "get_wireless_info"},
        )
        error_count = self.registry.get_sample_value(
            "asus_router_exporter_api_errors_total",
            {"method": "get_wireless_info"},
        )

        assert count == 1
        assert duration_count == 1
        assert error_count is None  # No errors

    def test_track_api_call_context_manager_error(self) -> None:
        """Test track_api_call context manager on error."""
        with pytest.raises(ValueError, match="test error"):
            with self.metrics.track_api_call("get_port_status"):
                time.sleep(0.01)  # Small delay to verify duration is recorded
                raise ValueError("test error")

        # Request count should NOT increment on error
        count = self.registry.get_sample_value(
            "asus_router_exporter_api_requests_total",
            {"method": "get_port_status"},
        )
        error_count = self.registry.get_sample_value(
            "asus_router_exporter_api_errors_total",
            {"method": "get_port_status"},
        )
        # Duration should still be recorded on error
        duration_count = self.registry.get_sample_value(
            "asus_router_exporter_api_request_duration_seconds_count",
            {"method": "get_port_status"},
        )
        duration_sum = self.registry.get_sample_value(
            "asus_router_exporter_api_request_duration_seconds_sum",
            {"method": "get_port_status"},
        )

        assert count is None  # No successful requests
        assert error_count == 1
        assert duration_count == 1  # Duration recorded even on error
        assert duration_sum >= 0.01  # At least the sleep time

    def test_track_api_call_records_duration(self) -> None:
        """Test that track_api_call records realistic duration."""
        sleep_time = 0.05

        with self.metrics.track_api_call("get_core_temp"):
            time.sleep(sleep_time)

        duration_sum = self.registry.get_sample_value(
            "asus_router_exporter_api_request_duration_seconds_sum",
            {"method": "get_core_temp"},
        )

        # Duration should be at least the sleep time
        assert duration_sum >= sleep_time
        # But not unreasonably longer
        assert duration_sum < sleep_time + 0.05


class TestCircuitBreakerStateValue:
    """Tests for CircuitBreakerStateValue enum."""

    def test_enum_values(self) -> None:
        """Test enum values match expected integers."""
        assert CircuitBreakerStateValue.CLOSED == 0
        assert CircuitBreakerStateValue.OPEN == 1
        assert CircuitBreakerStateValue.HALF_OPEN == 2

    def test_enum_is_int(self) -> None:
        """Test enum values can be used as integers."""
        assert int(CircuitBreakerStateValue.CLOSED) == 0
        assert int(CircuitBreakerStateValue.OPEN) == 1
        assert int(CircuitBreakerStateValue.HALF_OPEN) == 2
