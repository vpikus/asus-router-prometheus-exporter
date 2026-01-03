"""Pytest configuration and fixtures for all tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from asus_router_exporter.metrics.self_metrics import SelfMetrics


@pytest.fixture(autouse=True)
def reset_self_metrics() -> Generator[None, None, None]:
    """Reset SelfMetrics singleton before each test to avoid registry conflicts."""
    SelfMetrics.reset_instance()
    yield
    SelfMetrics.reset_instance()
