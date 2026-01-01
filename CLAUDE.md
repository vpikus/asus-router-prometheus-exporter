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
```

Environment variables: `ASUS_ROUTER_HOST`, `ASUS_ROUTER_AUTH`, `ASUS_METRICS_PORT` (default: 8000), `ASUS_LOG_LEVEL` (default: INFO)

## Architecture

```
asus_router_prometheus.py     # Main exporter - defines Prometheus metrics, RouterMetricsCollector
       ↓
asus_router_client.py         # HTTP client for ASUS router API (appGet.cgi hooks)
       ↓
asus_router_models.py         # Dataclasses and enums for router data structures
asus_router_utils.py          # Parsing helpers (MAC validation, hex parsing, etc.)
asus_router_client_exceptions.py  # AuthenticationException
```

**Key classes:**
- `RouterMetricsCollector` (prometheus): Orchestrates metric collection every 2 seconds via `collect_all_metrics()`
- `RouterClient` (client): Wraps HTTP requests to router's `/appGet.cgi` endpoint using hooks like `cpu_usage()`, `memory_usage()`, `netdev(appobj)`
- `RouterClientFactory` (client): Creates authenticated client instances

**Metric collection pattern:** Each `_collect_*_metrics()` method fetches data from RouterClient, calculates deltas for counters, and updates Prometheus metrics with labels.

## Router API

The exporter communicates with the ASUS router web interface at `/appGet.cgi` using "hooks" - special function calls that return JSON data. Examples:
- `cpu_usage()` - per-CPU usage stats
- `memory_usage()` - RAM utilization
- `netdev(appobj)` - network interface throughput
- Temperature data comes from `/ajax_coretmp.asp`
