# ASUS Router Prometheus Exporter

A Prometheus exporter for ASUS routers that collects and exposes metrics about router health, network performance, connected clients, and more.

## Features

- **Comprehensive metrics**: CPU, memory, temperature, network throughput, WAN status, wireless info, connected clients, port status
- **Auto re-authentication**: Automatically re-authenticates when router session expires
- **Error resilience**: Circuit breaker and retry mechanisms for fault tolerance
- **Stale metric protection**: Automatically clears metrics on collection failure to prevent stale data
- **Modular architecture**: Enable/disable specific collectors via configuration
- **Multiple configuration options**: Environment variables, YAML config files, or CLI arguments
- **Sensitive data masking**: Credentials, IPs, and MACs are masked in logs

## Installation

### Using pip

```bash
pip install asus-router-exporter
```

### From source

```bash
git clone https://github.com/vpikus/asus-router-prometheus-exporter.git
cd asus-router-prometheus-exporter
pip install -e .
```

## Usage

### Command Line

```bash
# Using command-line arguments
asus-router-exporter --router-host 192.168.1.1 --router-auth admin:password

# Using environment variables
export ASUS_ROUTER_HOST=192.168.1.1
export ASUS_ROUTER_AUTH=admin:password
asus-router-exporter

# Using a config file
asus-router-exporter --config config.yaml

# With custom port and log level
asus-router-exporter --router-host 192.168.1.1 --router-auth admin:password \
    --metrics-port 9100 --log-level DEBUG
```

### Docker

```bash
docker run -d \
  -e ASUS_ROUTER_HOST=192.168.1.1 \
  -e ASUS_ROUTER_AUTH=admin:password \
  -p 8000:8000 \
  asus-router-exporter
```

Or using docker-compose:

```yaml
version: '3'
services:
  asus-exporter:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ASUS_ROUTER_HOST=192.168.1.1
      - ASUS_ROUTER_AUTH=admin:password
```

### Programmatic Usage

```python
from asus_router_exporter import Container, Exporter
from asus_router_exporter.collectors import (
    CPUCollector, MemoryCollector, NetdevCollector,
    WANCollector, WirelessCollector, ClientsCollector,
    PortsCollector, RouterInfoCollector
)

# Create container from config
container = Container.from_config("config.yaml")

# Or from environment variables
container = Container.from_env()

# Register collectors
container.register_collectors(
    CPUCollector, MemoryCollector, NetdevCollector,
    WANCollector, WirelessCollector, ClientsCollector,
    PortsCollector, RouterInfoCollector
)

# Initialize and run
container.initialize()
exporter = Exporter(container)
exporter.run()
```

## Configuration

All configuration options can be set via environment variables, YAML config files, or CLI arguments.

### Environment Variables

#### Router Connection

| Variable | Description | Default |
|----------|-------------|---------|
| `ASUS_ROUTER_HOST` | Router IP address or hostname | `192.168.1.1` |
| `ASUS_ROUTER_AUTH` | Authentication (`username:password`) | Required |
| `ASUS_ROUTER_TIMEOUT` | Request timeout in seconds | `10` |

#### Exporter Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ASUS_METRICS_PORT` | Metrics HTTP port | `8000` |
| `ASUS_SCRAPE_INTERVAL` | Collection interval in seconds | `30` |
| `ASUS_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

#### Error Handling - Retry

| Variable | Description | Default |
|----------|-------------|---------|
| `ASUS_RETRY_ENABLED` | Enable retry mechanism | `true` |
| `ASUS_RETRY_MAX_ATTEMPTS` | Maximum retry attempts | `3` |
| `ASUS_RETRY_BACKOFF_FACTOR` | Exponential backoff factor | `2.0` |
| `ASUS_RETRY_MAX_DELAY` | Maximum delay between retries (seconds) | `30.0` |

#### Error Handling - Circuit Breaker

| Variable | Description | Default |
|----------|-------------|---------|
| `ASUS_CIRCUIT_BREAKER_ENABLED` | Enable circuit breaker | `true` |
| `ASUS_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | Failures before circuit opens | `5` |
| `ASUS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | Recovery timeout in seconds | `60.0` |
| `ASUS_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS` | Max calls in half-open state | `3` |

#### Collectors

| Variable | Description | Default |
|----------|-------------|---------|
| `ASUS_COLLECTOR_CPU_ENABLED` | Enable CPU metrics | `true` |
| `ASUS_COLLECTOR_MEMORY_ENABLED` | Enable memory metrics | `true` |
| `ASUS_COLLECTOR_TEMPERATURE_ENABLED` | Enable temperature metrics | `true` |
| `ASUS_COLLECTOR_NETWORK_ENABLED` | Enable network metrics | `true` |
| `ASUS_COLLECTOR_WAN_ENABLED` | Enable WAN metrics | `true` |
| `ASUS_COLLECTOR_WIRELESS_ENABLED` | Enable wireless metrics | `true` |
| `ASUS_COLLECTOR_PORTS_ENABLED` | Enable port metrics | `true` |
| `ASUS_COLLECTOR_CLIENTS_ENABLED` | Enable client metrics | `true` |
| `ASUS_COLLECTOR_SYSTEM_ENABLED` | Enable system/router info metrics | `true` |

#### Boolean Environment Variables

Boolean values accept: `true`, `1`, `yes`, `on` (truthy) or `false`, `0`, `no`, `off` (falsy), case-insensitive.

### YAML Configuration

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
  netdev:
    enabled: true
  wan:
    enabled: true
  wireless:
    enabled: true
  clients:
    enabled: true
  ports:
    enabled: true
  router_info:
    enabled: true

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

## Available Metrics

### Exporter Status
| Metric | Description |
|--------|-------------|
| `asus_router_up` | Whether the last scrape was successful (1=success, 0=failure) |
| `asus_router_scrape_duration_seconds` | Duration of the last scrape |

### Router Info
| Metric | Description |
|--------|-------------|
| `asus_router_info` | Router information (product_id, firmware, serial, hostname, mac) |
| `asus_router_uptime_seconds` | Router uptime in seconds |
| `asus_router_sw_mode` | Router software mode (one-hot encoded) |
| `asus_router_reboot_schedule_second_until_next` | Seconds until next scheduled reboot |
| `asus_router_software_update_available` | Whether software update is available |

### CPU
| Metric | Description |
|--------|-------------|
| `asus_router_cpu_temperature_celsius` | CPU temperature |
| `asus_router_cpu_usage` | CPU usage time (counter) |
| `asus_router_cpu_total` | CPU total time (counter) |
| `asus_router_cpu_usage_percent` | CPU usage percentage |

### Memory
| Metric | Description |
|--------|-------------|
| `asus_router_memory_total_bytes` | Total memory |
| `asus_router_memory_used_bytes` | Used memory |
| `asus_router_memory_free_bytes` | Free memory |
| `asus_router_memory_used_percent` | Memory usage percentage |

### Network (per interface)
| Metric | Description |
|--------|-------------|
| `asus_router_netdev_bridge_transmit_bytes_total` | Bridge TX bytes |
| `asus_router_netdev_bridge_receive_bytes_total` | Bridge RX bytes |
| `asus_router_netdev_wired_transmit_bytes_total` | Wired TX bytes |
| `asus_router_netdev_wired_receive_bytes_total` | Wired RX bytes |
| `asus_router_netdev_internet_transmit_bytes_total` | Internet TX bytes |
| `asus_router_netdev_internet_receive_bytes_total` | Internet RX bytes |
| `asus_router_netdev_wireless_transmit_bytes_total` | Wireless TX bytes |
| `asus_router_netdev_wireless_receive_bytes_total` | Wireless RX bytes |

### WAN
| Metric | Description |
|--------|-------------|
| `asus_router_dualwan_enabled` | Dual WAN enabled |
| `asus_router_dualwan_mode` | Dual WAN mode (one-hot) |
| `asus_router_link_internet_status` | Link internet status |
| `asus_router_wan_connection_state` | WAN state (one-hot) |
| `asus_router_wan_connection_substate` | WAN substate (one-hot) |
| `asus_router_wan_connection_auxstate` | WAN auxstate (one-hot) |
| `asus_router_wan_connection_online` | WAN online status |
| `asus_router_wan_status` | WAN status (one-hot) |
| `asus_router_wan_active` | WAN active |

### Wireless
| Metric | Description |
|--------|-------------|
| `asus_router_wireless_wps_enabled` | WPS enabled |
| `asus_router_wireless_smart_connect_enabled` | Smart Connect enabled |
| `asus_router_wireless_band` | Band info (SSID, MAC) |
| `asus_router_wireless_band_mode` | Band mode (one-hot) |
| `asus_router_wireless_auth_mode` | Auth mode (one-hot) |
| `asus_router_wireless_crypto` | Crypto mode (one-hot) |
| `asus_router_wireless_ssid_hidden` | SSID hidden |

### Clients
| Metric | Description |
|--------|-------------|
| `asus_router_client_info` | Client metadata (ipaddr, name, vendor) |
| `asus_router_client_operation_mode` | Operation mode (one-hot) |
| `asus_router_client_ip_method` | IP method (one-hot) |
| `asus_router_client_interface` | Connection interface (one-hot) |
| `asus_router_client_online` | Online status |
| `asus_router_client_last_conn_timestamp` | Last connection timestamp |
| `asus_router_client_conn_duration_seconds` | Connection duration |
| `asus_router_client_internet_mode` | Internet mode (one-hot) |
| `asus_router_client_internet_state` | Internet state |
| `asus_router_client_rssi_dbm` | RSSI signal strength |
| `asus_router_client_rssi_strength` | RSSI strength category (one-hot) |
| `asus_router_client_netdev_rx_bytes_total` | Client RX bytes |
| `asus_router_client_netdev_tx_bytes_total` | Client TX bytes |
| `asus_router_client_netdev_rx_throughput_bps` | Client RX throughput |
| `asus_router_client_netdev_tx_throughput_bps` | Client TX throughput |
| `asus_router_client_amesh_role` | AiMesh role (one-hot) |

### Ports
| Metric | Description |
|--------|-------------|
| `asus_router_ports_plugged` | Port plugged status |
| `asus_router_ports_link_rate_mbps` | Current link rate |
| `asus_router_ports_max_rate_mbps` | Maximum supported rate |
| `asus_router_ports_slow_speed` | Operating at reduced speed |
| `asus_router_ports_group` | Port group (one-hot) |
| `asus_router_ports_port` | Port info |

## Prometheus Configuration

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'asus_router'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 30s
```

## Alerting Examples

```yaml
groups:
  - name: asus_router
    rules:
      - alert: RouterDown
        expr: asus_router_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "ASUS router exporter is down"

      - alert: HighCPUUsage
        expr: asus_router_cpu_usage_percent > 90
        for: 5m
        labels:
          severity: warning

      - alert: HighMemoryUsage
        expr: asus_router_memory_used_percent > 90
        for: 5m
        labels:
          severity: warning

      - alert: WANOffline
        expr: asus_router_wan_connection_online == 0
        for: 1m
        labels:
          severity: critical
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check src/

# Run type checker
mypy src/
```

## License

MIT License
