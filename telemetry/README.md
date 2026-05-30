# OpenTelemetry Visualization Suite

A complete Docker-based setup for visualizing OpenTelemetry data using Grafana, including a sample FastAPI application with comprehensive instrumentation.

## Components

- **Grafana**: Visualization dashboard
- **Prometheus**: Metrics storage
- **Tempo**: Distributed tracing backend
- **Loki**: Log aggregation
- **OpenTelemetry Collector**: Centralized telemetry collection
- **FastAPI Example App**: Sample application with full OTel instrumentation

## Quick Start

1. Start the infrastructure:

   ```bash
   docker compose up -d
   ```

2. Run the example application:

   ```bash
   cd examples
   uv run python app.py
   ```

3. Access Grafana at <http://localhost:3010> (admin/admin)

4. Generate some traffic:

   ```bash
   # From examples directory
   curl http://localhost:8000/
   curl http://localhost:8000/api/users/123
   curl -X POST http://localhost:8000/api/orders -H "Content-Type: application/json" -d '{"items": [{"name": "item1", "price": 10}]}'
   ```

## Project Structure

```txt
.
├── config/                 # Configuration files
│   ├── otel/              # OpenTelemetry Collector config
│   ├── prometheus/        # Prometheus config
│   ├── tempo/             # Tempo config
│   └── loki/              # Loki config
├── grafana/               # Grafana provisioning (see grafana/README.md)
│   ├── dashboards/        # Dashboard JSON files
│   └── provisioning/      # Datasource configurations
├── examples/              # Example FastAPI application
└── compose.yaml          # Docker Compose orchestration
```

## Architecture

```txt
FastAPI App → OTel Collector → ┌─ Prometheus (Metrics)
                               ├─ Tempo (Traces)
                               └─ Loki (Logs)
                                     ↓
                                 Grafana
                                     ↑
Emulator Stack ──────────────────────┘
  ├─ Qdrant (native /metrics)
  ├─ elasticsearch-exporter
  └─ postgres-exporter
```

📊 [Detailed Architecture Diagram](docs/architecture-diagram.md)

## Port Configuration and Component Connections

### Port Mapping

| Service | Internal Port | External Port | Purpose |
|---------|--------------|---------------|---------|
| Grafana | 3000 | 3010 | Web UI (避けたport 3000をマッピング) |
| Prometheus | 9090 | 9091 | Metrics storage (避けたport 9090をマッピング) |
| Tempo | 3200 | 3200 | Trace storage |
| Loki | 3100 | 3100 | Log aggregation |
| OTel Collector | 4317 | 4317 | OTLP gRPC receiver |
| OTel Collector | 4318 | 4318 | OTLP HTTP receiver |
| OTel Collector | 8888 | 8888 | Collector metrics |
| OTel Collector | 8889 | 8889 | Prometheus exporter |
| FastAPI App | 8000 | - | Application (Docker外で実行) |

### Configuration Flow

#### 1. FastAPI → OpenTelemetry Collector

- **Connection**: `localhost:4317` (gRPC)
- **Config**: FastAPI app uses environment variable `OTEL_EXPORTER_OTLP_ENDPOINT="localhost:4317"`
- **Data**: Traces, Metrics, Logs

#### 2. OpenTelemetry Collector → Backend Services

- **Config File**: `config/otel/otel-collector-config.yaml`
- **Exporters**:
  - **Prometheus**: `endpoint: "0.0.0.0:8889"` - Metrics exposed for Prometheus to scrape
  - **Tempo**: `endpoint: tempo:4317` - Traces sent via internal Docker network
  - **Loki**: `endpoint: http://loki:3100/loki/api/v1/push` - Logs pushed to Loki

#### 3. Prometheus → OpenTelemetry Collector

- **Config File**: `config/prometheus/prometheus.yml`
- **Scrape Config**:

  ```yaml
  targets: ['otel-collector:8888', 'otel-collector:8889']
  ```

- **Connection**: Prometheus pulls metrics from OTel Collector's exposed endpoints

#### 4. Grafana → Data Sources

- **Config Files**: `grafana/provisioning/datasources/datasources.yaml`
- **Connections**:
  - **Prometheus**: `http://prometheus:9090` (internal Docker network)
  - **Tempo**: `http://tempo:3200` (internal Docker network)
  - **Loki**: `http://loki:3100` (internal Docker network)

### Docker Network Communication

- All services communicate via Docker's internal network using service names
- Only necessary ports are exposed to the host machine
- FastAPI runs outside Docker and connects to OTel Collector via exposed ports

## Features

- Automatic trace correlation across services
- Custom business metrics
- Structured logging with trace IDs
- Pre-configured Grafana dashboard
- Health check endpoints
- Example API with various telemetry patterns

## Configuration Details

### OpenTelemetry Collector (`config/otel/otel-collector-config.yaml`)

- **Receivers**: OTLP (gRPC:4317, HTTP:4318) - Receives telemetry from applications
- **Processors**: Batch processor for efficient data handling
- **Exporters**:
  - Prometheus (metrics) - Exposes metrics on port 8889
  - Tempo (traces) - Sends to `tempo:4317`
  - Loki (logs) - Sends to `http://loki:3100`

### Prometheus (`config/prometheus/prometheus.yml`)

- Scrapes metrics from OTel Collector every 15 seconds
- Targets: `otel-collector:8888` (collector internal metrics) and `otel-collector:8889` (application metrics)

### Tempo (`config/tempo/tempo-config.yaml`)

- Receives traces on port 4317 (internal)
- Stores traces locally with 1-hour retention
- Accessible via HTTP on port 3200

### Loki (`config/loki/loki-config.yaml`)

- Receives logs via HTTP push on port 3100
- Uses filesystem storage for logs
- WAL disabled for simplified setup

### Grafana Provisioning

- **Data Sources** (`grafana/provisioning/datasources/datasources.yaml`):
  - Automatically configures Prometheus, Tempo, and Loki connections
- **Dashboards** (`grafana/provisioning/dashboards/dashboards.yaml`):
  - Auto-loads dashboards from `/var/lib/grafana/dashboards`
- **Pre-configured Dashboard** (`grafana/dashboards/opentelemetry-overview.json`):
  - Request rate metrics
  - Request duration percentiles (p95, p99)
  - Recent traces table
  - Application logs viewer

## Emulator Metrics Integration

The telemetry stack scrapes metrics from the `emulator` stack via the shared Docker network `shared-otel-net`.

### Scraped Services

| Service | Target | Metrics Path | Scrape Interval |
|---------|--------|--------------|-----------------|
| Qdrant | `qdrant-emulator:6333` | `/metrics` | 30s |
| Elasticsearch | `elasticsearch-exporter:9114` | `/metrics` | 30s |
| PostgreSQL | `postgres-exporter:9187` | `/metrics` | 30s |

> Note: Neo4j Community Edition does not support Prometheus metrics (Enterprise only).

### Configuration

Scrape targets are defined in `config/otel/otel-collector-config.yaml`:

```yaml
prometheus:
  config:
    scrape_configs:
      - job_name: 'qdrant'
        static_configs:
          - targets: ['qdrant-emulator:6333']
      - job_name: 'elasticsearch'
        static_configs:
          - targets: ['elasticsearch-exporter:9114']
      - job_name: 'postgres'
        static_configs:
          - targets: ['postgres-exporter:9187']
```

### Grafana Dashboard

Pre-configured dashboard: **Emulator Metrics** (`grafana/dashboards/emulator-metrics.json`)

Panels include:
- **Qdrant**: Collections, vectors, search time
- **Elasticsearch**: Cluster health, nodes, JVM memory, document count
- **PostgreSQL**: Status, database size, active connections

### Network Setup

Both stacks share the Docker network `shared-otel-net` (declared `external` in
each `compose.yaml`). The repo-root `just` recipes create it idempotently, so no
manual `docker network create` is needed:

```bash
# from the dotfiles repo root — each ensures shared-otel-net exists first
just tel-up      # start telemetry stack (otel + grafana + loki + prometheus + tempo)
just emu-up      # start emulator stack (datastores + inspectors)
```

To wire it up by hand instead (e.g. outside the repo), create the network first:

```bash
docker network create shared-otel-net   # idempotent; skip if it already exists
cd telemetry && docker compose up -d
cd emulator  && docker compose up -d
```

## Troubleshooting

### Port Conflicts

If you encounter port conflicts, check the Port Configuration table above and ensure no other services are using these ports.

### FastAPI Connection Issues

Ensure the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable is set correctly:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="localhost:4317"
```

### No Data in Grafana

1. Check all Docker containers are running: `docker compose ps`
2. Verify FastAPI app is sending data (check logs)
3. Wait a few seconds for data to propagate through the pipeline
