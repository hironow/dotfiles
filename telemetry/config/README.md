# Configuration Files

This directory contains all configuration files for the OpenTelemetry stack:

## Directory Structure

- `otel/` - OpenTelemetry Collector configuration
  - `otel-collector-config.yaml` - Main collector configuration with receivers, processors, and exporters
  
- `prometheus/` - Prometheus configuration
  - `prometheus.yml` - Prometheus scrape configuration
  
- `tempo/` - Tempo configuration
  - `tempo-config.yaml` - Tempo distributed tracing backend configuration
  
- `loki/` - Loki configuration
  - `loki-config.yaml` - Loki log aggregation configuration

## Key Configuration Details

### OpenTelemetry Collector

- Receives telemetry data via OTLP (gRPC on port 4317, HTTP on port 4318)
- Exports traces to Tempo, metrics to Prometheus, and logs to Loki

### Prometheus

- Scrapes metrics from the OpenTelemetry Collector
- Exposed on port 9091 (to avoid conflict with local development)

### Tempo

- Stores distributed traces
- Exposed on port 3200

### Loki

- Aggregates logs from applications
- Exposed on port 3100
