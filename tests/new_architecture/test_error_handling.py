"""
Tests for the error handling module.
"""

import sys
import time
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, 'src')

from asus_router_exporter.core.error_handling import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CompositeErrorHandler,
    RetryConfig,
    RetryHandler,
)
from asus_router_exporter.core.exceptions import (
    CircuitBreakerOpenError,
    RetryExhaustedError,
)


class TestRetryHandler:
    """Tests for RetryHandler."""

    def test_successful_execution_no_retry(self):
        handler = RetryHandler(RetryConfig(max_attempts=3))
        mock_func = Mock(return_value="success")

        result = handler.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_failure(self):
        handler = RetryHandler(RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
            backoff_factor=1.0
        ))
        mock_func = Mock(side_effect=[Exception("fail"), Exception("fail"), "success"])

        result = handler.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_exhausted_retries_raises_error(self):
        handler = RetryHandler(RetryConfig(
            max_attempts=3,
            initial_delay=0.01
        ))
        error = ValueError("persistent error")
        mock_func = Mock(side_effect=error)

        with pytest.raises(RetryExhaustedError) as exc_info:
            handler.execute(mock_func)

        assert exc_info.value.attempts == 3
        assert exc_info.value.last_error is error

    def test_disabled_retry_propagates_error(self):
        handler = RetryHandler(RetryConfig(enabled=False))
        mock_func = Mock(side_effect=ValueError("error"))

        with pytest.raises(ValueError):
            handler.execute(mock_func)

        assert mock_func.call_count == 1

    def test_exponential_backoff(self):
        with patch('asus_router_exporter.core.error_handling.time.sleep') as mock_sleep:
            handler = RetryHandler(RetryConfig(
                max_attempts=4,
                initial_delay=1.0,
                backoff_factor=2.0,
                max_delay=10.0
            ))
            mock_func = Mock(side_effect=[
                Exception(), Exception(), Exception(), "success"
            ])

            handler.execute(mock_func)

            # Check sleep calls: 1.0, 2.0, 4.0
            assert mock_sleep.call_count == 3
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert delays == [1.0, 2.0, 4.0]

    def test_max_delay_cap(self):
        with patch('asus_router_exporter.core.error_handling.time.sleep') as mock_sleep:
            handler = RetryHandler(RetryConfig(
                max_attempts=5,
                initial_delay=1.0,
                backoff_factor=10.0,
                max_delay=5.0
            ))
            mock_func = Mock(side_effect=[
                Exception(), Exception(), Exception(), Exception(), "success"
            ])

            handler.execute(mock_func)

            # Delays should be capped at max_delay
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert all(d <= 5.0 for d in delays)

    def test_retry_only_specified_exceptions(self):
        handler = RetryHandler(RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
            retryable_exceptions=(ValueError,)
        ))

        # ValueError should be retried
        mock_func = Mock(side_effect=[ValueError(), "success"])
        result = handler.execute(mock_func)
        assert result == "success"

        # TypeError should not be retried
        mock_func = Mock(side_effect=TypeError("not retryable"))
        with pytest.raises(TypeError):
            handler.execute(mock_func)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_closed_state_allows_execution(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        mock_func = Mock(return_value="success")

        result = breaker.execute(mock_func)

        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=60.0
        ))

        for _ in range(3):
            with pytest.raises(Exception):
                breaker.execute(Mock(side_effect=Exception()))

        assert breaker.state == CircuitState.OPEN

    def test_open_state_blocks_execution(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=60.0
        ))

        # Trigger open state
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        assert breaker.state == CircuitState.OPEN

        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            breaker.execute(Mock(return_value="success"))

    def test_transitions_to_half_open_after_recovery(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1
        ))

        # Trigger open state
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Next execution attempt should transition to half-open
        result = breaker.execute(Mock(return_value="success"))
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_closes_on_success(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.01
        ))

        # Trigger open state
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        time.sleep(0.02)

        # Successful execution should close the circuit
        breaker.execute(Mock(return_value="success"))
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_reopens_on_failure(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.01
        ))

        # Trigger open state
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        time.sleep(0.02)

        # Failed execution should reopen the circuit
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        assert breaker.state == CircuitState.OPEN

    def test_disabled_circuit_breaker(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(enabled=False))

        # Should not open even after many failures
        for _ in range(10):
            with pytest.raises(Exception):
                breaker.execute(Mock(side_effect=Exception()))

        # Should still allow execution
        result = breaker.execute(Mock(return_value="success"))
        assert result == "success"

    def test_reset(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=60.0
        ))

        # Trigger open state
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        assert breaker.state == CircuitState.OPEN

        # Reset should close circuit
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_max_calls(self):
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.01,
            half_open_max_calls=2
        ))

        # Trigger open state
        with pytest.raises(Exception):
            breaker.execute(Mock(side_effect=Exception()))

        time.sleep(0.02)

        # Manually set state to HALF_OPEN and simulate max calls reached
        breaker._state.state = CircuitState.HALF_OPEN
        breaker._state.half_open_calls = 2  # At max_calls limit

        # Next call should be blocked because max half-open calls reached
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            breaker.execute(Mock(return_value="success"))

        assert "max test calls reached" in str(exc_info.value)


class TestCompositeErrorHandler:
    """Tests for CompositeErrorHandler."""

    def test_successful_execution(self):
        handler = CompositeErrorHandler(
            retry_config=RetryConfig(max_attempts=3),
            circuit_config=CircuitBreakerConfig(failure_threshold=5)
        )
        mock_func = Mock(return_value="success")

        result = handler.execute(mock_func)

        assert result == "success"

    def test_retry_before_circuit_opens(self):
        handler = CompositeErrorHandler(
            retry_config=RetryConfig(max_attempts=2, initial_delay=0.01),
            circuit_config=CircuitBreakerConfig(failure_threshold=5)
        )

        # Function fails then succeeds
        mock_func = Mock(side_effect=[Exception(), "success"])

        result = handler.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 2

    def test_circuit_opens_after_retry_exhaustion(self):
        handler = CompositeErrorHandler(
            retry_config=RetryConfig(max_attempts=2, initial_delay=0.01),
            circuit_config=CircuitBreakerConfig(failure_threshold=2)
        )

        # Multiple failures should eventually open circuit
        for _ in range(2):
            with pytest.raises(RetryExhaustedError):
                handler.execute(Mock(side_effect=Exception()))

        # Circuit should now be open
        assert handler.circuit_breaker.state == CircuitState.OPEN

    def test_from_config(self):
        config = Mock()
        config.get.side_effect = lambda key, default={}: {
            'error_handling': {
                'retry': {
                    'enabled': True,
                    'max_attempts': 5,
                    'backoff_factor': 3.0,
                    'max_delay': 60.0
                },
                'circuit_breaker': {
                    'enabled': True,
                    'failure_threshold': 10,
                    'recovery_timeout': 120.0,
                    'half_open_max_calls': 5
                }
            }
        }.get(key, default)

        handler = CompositeErrorHandler.from_config(config)

        assert handler.retry_handler.config.max_attempts == 5
        assert handler.retry_handler.config.backoff_factor == 3.0
        assert handler.circuit_breaker.config.failure_threshold == 10
        assert handler.circuit_breaker.config.recovery_timeout == 120.0
