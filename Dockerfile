# syntax=docker/dockerfile:1

# Stage 1: Build dependencies
FROM python:3.12-alpine AS builder

WORKDIR /app

# Install Python dependencies with BuildKit cache for faster rebuilds
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip wheel setuptools && \
    python -m pip install --prefix=/install -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-alpine AS runtime

# Build arguments for labels
ARG VERSION=dev
ARG BUILD_DATE
ARG VCS_REF

# OCI Image Labels (https://github.com/opencontainers/image-spec/blob/main/annotations.md)
LABEL org.opencontainers.image.title="ASUS Router Prometheus Exporter" \
      org.opencontainers.image.description="Prometheus metrics exporter for ASUS routers" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/vpikus/asus-router-prometheus-exporter" \
      org.opencontainers.image.url="https://github.com/vpikus/asus-router-prometheus-exporter" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="vpikus"

WORKDIR /app

# Install runtime dependencies
# ca-certificates: for HTTPS connections to router
RUN apk add --no-cache ca-certificates

# Create non-root user and data directory for potential future state/logs
RUN addgroup -g 1000 exporter && \
    adduser -u 1000 -G exporter -s /bin/sh -D exporter && \
    mkdir -p /app/data && \
    chown exporter:exporter /app/data

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=exporter:exporter src/ ./src/

# Switch to non-root user
USER exporter

# Expose metrics port
EXPOSE 8000

# Health check with conservative settings
# - Start period of 30s allows time for initial router connection
# - Increased timeout for slow router responses
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"ASUS_METRICS_PORT\", \"8000\")}/metrics', timeout=10)"

# Set environment defaults
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app/src" \
    ASUS_METRICS_PORT=8000 \
    ASUS_LOG_LEVEL=INFO

# Use ENTRYPOINT for predictable execution; CMD can be overridden for args
ENTRYPOINT ["python", "-m", "asus_router_exporter.cli"]
CMD []
