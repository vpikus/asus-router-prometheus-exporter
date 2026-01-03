"""Decorators for the router client API methods."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

from ..metrics.self_metrics import SelfMetrics

# Type variable for the decorator return type
_F = TypeVar("_F", bound=Callable[..., Any])


def track_api(method_name: str) -> Callable[[_F], _F]:
    """
    Decorator to track API method performance metrics.

    Args:
        method_name: Name to use in metrics (e.g., 'get_cpu_usage')

    Returns:
        Decorated function that records request count, duration, and errors

    Note:
        Caches the SelfMetrics instance on first call to avoid lock acquisition
        on every API invocation.
    """

    def decorator(func: _F) -> _F:
        # Use mutable list as closure to cache metrics instance across calls,
        # avoiding get_instance() lock acquisition on every API invocation
        cached_metrics: list[SelfMetrics | None] = [None]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if cached_metrics[0] is None:
                cached_metrics[0] = SelfMetrics.get_instance()
            with cached_metrics[0].track_api_call(method_name):
                return func(*args, **kwargs)

        return cast(_F, wrapper)

    return decorator
