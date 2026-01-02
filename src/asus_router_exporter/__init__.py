"""
ASUS Router Prometheus Exporter.

A modular, extensible Prometheus exporter for ASUS routers.

Example:
    from asus_router_exporter import Container, Exporter
    from asus_router_exporter.collectors import CPUCollector, MemoryCollector

    container = Container.from_config("config.yaml")
    container.register_collectors(CPUCollector, MemoryCollector)
    container.initialize()

    exporter = Exporter(container)
    exporter.run()
"""

from .core import (
    AuthenticationError,
    CollectorError,
    Config,
    ConfigurationError,
    Container,
    ExporterError,
    RouterConnectionError,
)
from .server import Exporter, create_exporter

__version__ = "2.0.0"

__all__ = [
    # Core
    "Config",
    "Container",
    # Server
    "Exporter",
    "create_exporter",
    # Exceptions
    "ExporterError",
    "ConfigurationError",
    "AuthenticationError",
    "RouterConnectionError",
    "CollectorError",
    # Version
    "__version__",
]
