# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Prometheus metrics exporter for ASUS routers. Collects router metrics (CPU, memory, temperature, network throughput, connected clients, WAN status, WiFi info) and exposes them in Prometheus format on port 8000.

## Running the Exporter

```bash
# Local development
pip install -r requirements.txt
python asus_router_prometheus.py --router-host 192.168.1.1 --router-auth admin:password

# Using environment variables
export ASUS_ROUTER_HOST=192.168.1.1
export ASUS_ROUTER_AUTH=admin:password
python asus_router_prometheus.py

# Docker
docker-compose up --build

# Using new modular architecture (v2)
python -m asus_router_exporter.cli --router-host 192.168.1.1 --router-auth TOKEN
```

Environment variables: `ASUS_ROUTER_HOST`, `ASUS_ROUTER_AUTH`, `ASUS_METRICS_PORT` (default: 8000), `ASUS_LOG_LEVEL` (default: INFO)

## Architecture

### Legacy Architecture (v1)

```
asus_router_prometheus.py     # Main exporter - defines Prometheus metrics, RouterMetricsCollector
       ↓
asus_router_client.py         # HTTP client for ASUS router API (appGet.cgi hooks)
       ↓
asus_router_models.py         # Dataclasses and enums for router data structures
asus_router_utils.py          # Parsing helpers (MAC validation, hex parsing, etc.)
asus_router_client_exceptions.py  # AuthenticationException
```

### New Modular Architecture (v2)

```
src/asus_router_exporter/
├── __init__.py               # Package exports, version
├── cli.py                    # Command-line interface
├── core/
│   ├── config.py             # YAML + env var configuration management
│   ├── container.py          # Dependency injection container
│   ├── error_handling.py     # Retry handler + circuit breaker
│   ├── exceptions.py         # Custom exception classes
│   └── protocols.py          # Protocol (interface) definitions
├── collectors/
│   ├── base.py               # Abstract base collector class
│   └── cpu.py                # CPU metrics collector (proof of concept)
├── server/
│   └── exporter.py           # HTTP server and collection loop
├── client/                   # (future) Router client wrapper
├── metrics/                  # (future) Metric definitions
└── utils/                    # (future) Shared utilities
```

**Key Design Patterns:**

1. **Protocol-based Interfaces** (`core/protocols.py`)
   - `RouterClientProtocol`: Contract for router API clients
   - `MetricCollectorProtocol`: Contract for metric collectors
   - `ConfigProviderProtocol`: Contract for configuration access

2. **Dependency Injection** (`core/container.py`)
   - Manages component lifecycle
   - Enables easy testing with mock implementations
   - Lazy instantiation of expensive resources

3. **Error Handling** (`core/error_handling.py`)
   - `RetryHandler`: Exponential backoff retry
   - `CircuitBreaker`: Fail-fast pattern for fault tolerance
   - `CompositeErrorHandler`: Combines both strategies

4. **Modular Collectors** (`collectors/`)
   - `BaseCollector`: Abstract class with common functionality
   - Each collector handles specific metric category
   - Enable/disable via configuration

**Collector Pattern:**
```python
class CPUCollector(BaseCollector):
    name = "cpu"

    def _create_metrics(self):
        self._usage = Gauge("asus_router_cpu_usage_percent", ...)

    def _collect_metrics(self, router_client, router_info):
        usage = router_client.get_cpu_usage()
        self._usage.set(usage)
```

### Key Classes

**Legacy (v1):**
- `RouterMetricsCollector` (prometheus): Orchestrates metric collection every 2 seconds via `collect_all_metrics()`
- `RouterClient` (client): Wraps HTTP requests to router's `/appGet.cgi` endpoint using hooks like `cpu_usage()`, `memory_usage()`, `netdev(appobj)`
- `RouterClientFactory` (client): Creates authenticated client instances

**New (v2):**
- `Container`: Dependency injection container for all components
- `Config`: Configuration management with YAML and env vars support
- `BaseCollector`: Abstract base for all metric collectors
- `Exporter`: HTTP server and collection loop manager
- `CompositeErrorHandler`: Combined retry + circuit breaker

## Configuration

### Environment Variables (both v1 and v2)
- `ASUS_ROUTER_HOST`: Router IP address
- `ASUS_ROUTER_AUTH`: Authentication token (base64)
- `ASUS_METRICS_PORT`: Metrics HTTP port (default: 8000)
- `ASUS_SCRAPE_INTERVAL`: Collection interval in seconds (default: 30)
- `ASUS_LOG_LEVEL`: Log level (DEBUG, INFO, WARNING, ERROR)

### YAML Configuration (v2 only)
```yaml
router:
  host: ${ASUS_ROUTER_HOST:192.168.1.1}
  auth: ${ASUS_ROUTER_AUTH}
  timeout: 10

exporter:
  port: 8000
  scrape_interval: 30

collectors:
  cpu:
    enabled: true
  memory:
    enabled: true
  temperature:
    enabled: false  # Disable specific collector

error_handling:
  retry:
    enabled: true
    max_attempts: 3
    backoff_factor: 2.0
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    recovery_timeout: 60.0
```

## Router API

The exporter communicates with the ASUS router web interface at `/appGet.cgi` using "hooks" - special function calls that return JSON data. Examples:
- `cpu_usage()` - per-CPU usage stats
- `memory_usage()` - RAM utilization
- `netdev(appobj)` - network interface throughput
- Temperature data comes from `/ajax_coretmp.asp`

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run new architecture tests only
python -m pytest tests/new_architecture/ -v

# Run with coverage
python -m pytest tests/ --cov=src/asus_router_exporter
```

## Adding a New Collector

1. Create collector in `src/asus_router_exporter/collectors/`
2. Inherit from `BaseCollector`
3. Implement `name`, `_create_metrics()`, and `_collect_metrics()`
4. Register in container: `container.register_collector(MyCollector)`

Example:
```python
from asus_router_exporter.collectors.base import BaseCollector
from prometheus_client import Gauge

class MemoryCollector(BaseCollector):
    name = "memory"

    def _create_metrics(self):
        self._usage = self._register_metric(
            Gauge("asus_router_memory_usage_bytes", "Memory usage", ["product_id"])
        )

    def _collect_metrics(self, router_client, router_info):
        mem = router_client.get_memory_usage()
        self._usage.labels(product_id=router_info.product_id).set(mem.used)
```

## Logging

Sensitive data (IPs, MACs, credentials, SSIDs) is automatically masked in logs via `SensitiveFormatter` when `mask_sensitive=True` (default).
