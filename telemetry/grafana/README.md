# Grafana Configuration

This directory contains all Grafana-related configuration files and dashboards for automatic provisioning.

## Directory Structure

```txt
grafana/
├── provisioning/           # Auto-provisioning configuration
│   ├── datasources/       # Data source configurations
│   │   └── datasources.yaml
│   └── dashboards/        # Dashboard provisioning config
│       └── dashboards.yaml
└── dashboards/            # Dashboard JSON files
    └── opentelemetry-overview.json
```

## Provisioning Configuration

### Data Sources (`provisioning/datasources/datasources.yaml`)

Automatically configures three data sources when Grafana starts:

1. **Prometheus** (Default)
   - Type: `prometheus`
   - URL: `http://prometheus:9090` (internal Docker network)
   - Purpose: Metrics storage and queries

2. **Tempo**
   - Type: `tempo`
   - URL: `http://tempo:3200` (internal Docker network)
   - Purpose: Distributed tracing data

3. **Loki**
   - Type: `loki`
   - URL: `http://loki:3100` (internal Docker network)
   - Purpose: Log aggregation and queries

### Dashboard Provisioning (`provisioning/dashboards/dashboards.yaml`)

- Automatically loads all dashboards from `/var/lib/grafana/dashboards`
- Updates every 10 seconds
- Allows UI updates to dashboards

## Pre-configured Dashboard

### OpenTelemetry Overview (`dashboards/opentelemetry-overview.json`)

A comprehensive dashboard that visualizes:

#### Panels

1. **Request Rate**
   - Shows request rate over time grouped by endpoint and method
   - Query: `rate(http_requests_total[5m])`

2. **Active Requests**
   - Displays current number of active requests
   - Gauge visualization

3. **Request Duration (p95, p99)**
   - Shows 95th and 99th percentile request durations
   - Queries:
     - p95: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
     - p99: `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))`

4. **Recent Traces**
   - Table showing recent traces from Tempo
   - Displays: Trace ID, Service, Name, Start Time, Duration
   - Click on trace ID to explore in detail

5. **Application Logs**
   - Real-time log viewer from Loki
   - Filtered by service name: `fastapi-example`

#### Features

- Auto-refresh: Every 5 seconds
- Time range: Last 5 minutes (default)
- Template variables for datasource selection
- Dark theme

## How It Works

1. When Docker Compose starts Grafana, it mounts the `provisioning` directory
2. Grafana automatically reads the provisioning configurations
3. Data sources are created based on `datasources.yaml`
4. Dashboards are loaded from the location specified in `dashboards.yaml`
5. The OpenTelemetry Overview dashboard becomes immediately available

## Adding New Dashboards

1. Create a new dashboard JSON file in the `dashboards/` directory
2. Restart Grafana or wait for the auto-reload interval (10 seconds)
3. The dashboard will appear in Grafana's dashboard list

## Customizing Data Sources

To add or modify data sources, edit `provisioning/datasources/datasources.yaml` and restart Grafana.

## Access

- URL: <http://localhost:3010>
- Default credentials: admin/admin
- First login will prompt to change password (can skip)

## Tips

- All provisioned resources are marked as `editable: true`, so you can modify them via the UI
- Changes made in the UI won't persist across container restarts unless exported and saved to the JSON files
- To export a dashboard: Dashboard Settings → JSON Model → Copy and save to `dashboards/`
