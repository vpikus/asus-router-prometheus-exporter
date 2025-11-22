FROM python:3.11-alpine

# Set working directory
WORKDIR /app

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies in virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY asus_router_* .

# Create non-root user
RUN addgroup -g 1000 exporter && \
    adduser -D -u 1000 -G exporter exporter && \
    chown -R exporter:exporter /app && \
    chown -R exporter:exporter /opt/venv

# Switch to non-root user
USER exporter

# Expose metrics port
EXPOSE 8000

# Set environment variables for runtime configuration
ENV ASUS_METRICS_PORT=8000
ENV ASUS_LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/metrics').read()" || exit 1

RUN <<'EOT' cat > run && chmod 0755 run
#!/bin/sh

exec python ./asus_router_prometheus.py
EOT

# Run the exporter
CMD ["./run"]
