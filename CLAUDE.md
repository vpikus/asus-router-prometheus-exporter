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
│   ├── error_handling/       # Error handling package
│   │   ├── __init__.py       # Re-exports for backward compatibility
│   │   ├── retry.py          # RetryConfig + RetryHandler
│   │   ├── circuit_breaker.py # CircuitBreaker pattern
│   │   └── composite.py      # CompositeErrorHandler
│   ├── exceptions.py         # Custom exception classes
│   └── protocols.py          # Protocol (interface) definitions
├── collectors/
│   ├── __init__.py           # Exports DEFAULT_COLLECTORS list
│   ├── base.py               # Abstract base collector class
│   ├── cpu.py                # CPU temperature and usage metrics
│   ├── memory.py             # Memory usage metrics
│   ├── netdev.py             # Network device throughput metrics
│   ├── wan.py                # WAN connection and dual-WAN metrics
│   ├── wireless.py           # Wireless band and WiFi metrics
│   ├── ports.py              # Ethernet port status metrics
│   ├── clients.py            # Connected client metrics
│   └── router_info.py        # Router info, uptime, firmware metrics
├── server/
│   └── exporter.py           # HTTP server and collection loop
├── client/
│   ├── __init__.py           # Package exports (RouterClient, RouterClientFactory)
│   ├── router_client.py      # Router HTTP client with auto re-auth
│   ├── factory.py            # RouterClientFactory for authentication
│   ├── decorators.py         # @track_api decorator for metrics
│   └── models/               # Data models package
│       ├── __init__.py       # Re-exports all 50+ models
│       ├── system.py         # CPU, memory, uptime, temperature models
│       ├── network.py        # Throughput, netdev, traffic models
│       ├── wireless.py       # WiFi band, mode, auth models
│       ├── wan.py            # WAN, dual WAN, DSL, LAN models
│       ├── ports.py          # Ethernet/USB port models
│       ├── clients.py        # Connected client models
│       └── router.py         # RouterInfo, capabilities, SwMode
├── metrics/
│   ├── __init__.py           # Module exports
│   └── self_metrics.py       # Exporter self-observability metrics
└── utils/
    ├── logging.py            # Sensitive data masking formatter
    └── parsing.py            # Parsing helpers
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

3. **Error Handling** (`core/error_handling/`)
   - `retry.py`: `RetryHandler` with exponential backoff (skips non-recoverable auth errors)
   - `circuit_breaker.py`: `CircuitBreaker` fail-fast pattern for fault tolerance
   - `composite.py`: `CompositeErrorHandler` combines both strategies
   - Package re-exports all classes via `__init__.py` for backward compatibility

4. **Modular Collectors** (`collectors/`)
   - `BaseCollector`: Abstract class with common functionality
   - Each collector handles specific metric category
   - Enable/disable via configuration
   - Stale metric cleanup when interfaces/clients disappear

5. **Router Client** (`client/`)
   - `router_client.py`: HTTP client with auto re-authentication on session expiry
   - `factory.py`: `RouterClientFactory` for creating authenticated client instances with `authenticate_session()` helper
   - `decorators.py`: `@track_api` decorator for API call performance instrumentation
   - `models/`: Domain-organized data models (system, network, wan, wireless, ports, clients, router)
   - urllib3 retries disabled to allow application-level retry control
   - Smart authentication error handling to prevent account lockout
   - Cache hit/miss tracking for per-cycle caching
   - **Proactive re-authentication**: Configurable interval (default 30min) to re-authenticate before session expires, using monotonic time to avoid clock skew issues

6. **Self-Metrics** (`metrics/self_metrics.py`)
   - Thread-safe singleton `SelfMetrics` for exporter observability
   - Circuit breaker state and transition tracking
   - Retry attempt and exhaustion counters
   - Cache hit/miss counters per cache key
   - Per-collector success/error rates and duration
   - Per-API method performance histograms

7. **Authentication Exceptions** (`core/exceptions.py`)
   Router returns `error_status` codes that map to specific exceptions:
   - `SessionExpiredError` (error_status 1-2): Recoverable, triggers re-auth
   - `InvalidCredentialsError` (error_status 3, 7): NOT recoverable, no retry
   - `CaptchaRequiredError` (captcha_on=1): NOT recoverable, requires router config change
   - `AccountLockedError` (error_status 11): NOT recoverable, requires factory reset
   - `AuthenticationBlockedError` (error_status 4-6, 8-10, 12+): NOT recoverable

   **Important**: CAPTCHA check takes priority over error_status. Non-recoverable errors
   are never retried by `RetryHandler` to prevent triggering account lockout (which
   happens after 5 failed attempts at error_status 7, and requires factory reset at 11).

**Collector Pattern:**
```python
class CPUCollector(BaseCollector):
    name = "cpu"

    def _create_metrics(self):
        self._usage = Gauge(
            "asus_router_cpu_usage_percent",
            "CPU usage percentage",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._usage)  # Register for automatic cleanup

    def _collect_metrics(self, router_client, router_info):
        # Always use getattr() for safe fallback when router is unreachable
        product_id = getattr(router_info, 'product_id', 'unknown')
        usage = router_client.get_cpu_usage()
        self._usage.labels(product_id=product_id).set(usage)
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
- `RouterClientFactory`: Creates authenticated router client instances with auto re-authentication

## Configuration

### Environment Variables (both v1 and v2)
- `ASUS_ROUTER_HOST`: Router IP address
- `ASUS_ROUTER_AUTH`: Authentication token (base64)
- `ASUS_ROUTER_REAUTH_INTERVAL`: Proactive re-authentication interval in seconds (default: 1800 = 30min, 0 = disabled)
- `ASUS_METRICS_PORT`: Metrics HTTP port (default: 8000)
- `ASUS_SCRAPE_INTERVAL`: Collection interval in seconds (default: 30)
- `ASUS_LOG_LEVEL`: Log level (DEBUG, INFO, WARNING, ERROR)

### YAML Configuration (v2 only)
```yaml
router:
  host: ${ASUS_ROUTER_HOST:192.168.1.1}
  auth: ${ASUS_ROUTER_AUTH}
  timeout: 10
  reauth_interval: 1800  # Proactive re-auth interval (0 = disabled)

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
        # Always use getattr() for router_info fields for safe fallback
        product_id = getattr(router_info, 'product_id', 'unknown')
        mem = router_client.get_memory_usage()
        self._usage.labels(product_id=product_id).set(mem.used)
```

## Self-Metrics for Observability

The exporter exposes internal metrics about its own health and performance:

### Circuit Breaker Metrics
- `asus_router_exporter_circuit_breaker_state`: Current state (0=closed, 1=open, 2=half_open)
- `asus_router_exporter_circuit_breaker_failure_count`: Current consecutive failure count
- `asus_router_exporter_circuit_breaker_recovery_seconds`: Seconds until recovery attempt (0 when closed)
- `asus_router_exporter_circuit_breaker_state_transitions_total`: State transition counter by from/to labels

### Retry Metrics
- `asus_router_exporter_retry_attempts_total`: Total retry attempts (excludes initial)
- `asus_router_exporter_retries_exhausted_total`: Times all retries were exhausted

### Authentication Metrics
- `asus_router_exporter_proactive_reauth_total`: Total number of proactive re-authentications

### API Performance Metrics
- `asus_router_exporter_api_requests_total{method}`: API call counts by method
- `asus_router_exporter_api_request_duration_seconds{method}`: API call duration histogram
- `asus_router_exporter_api_errors_total{method}`: API error counts by method

### Collector Metrics
- `asus_router_exporter_collector_success_total{collector}`: Successful collections
- `asus_router_exporter_collector_errors_total{collector}`: Collection errors
- `asus_router_exporter_collector_duration_seconds{collector}`: Last collection duration

### Cache Metrics
- `asus_router_exporter_cache_hits_total{cache_key}`: Cache hits by key
- `asus_router_exporter_cache_misses_total{cache_key}`: Cache misses by key

## Logging

Sensitive data (IPs, MACs, credentials, SSIDs) is automatically masked in logs via `SensitiveFormatter` when `mask_sensitive=True` (default).
