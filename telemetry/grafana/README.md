# Grafana Configuration

Grafana loads its data sources and dashboards from this directory at start-up.
[`../compose.yaml`](../compose.yaml) mounts `provisioning/` at
`/etc/grafana/provisioning` and `dashboards/` at `/var/lib/grafana/dashboards`.

Open <http://localhost:3010> and sign in as admin/admin. You can skip the
password change on first login.

## Files

| File | What it sets up |
| --- | --- |
| [`provisioning/datasources/datasources.yaml`](provisioning/datasources/datasources.yaml) | Prometheus (default), Tempo and Loki, by service name on the Docker network |
| [`provisioning/dashboards/dashboards.yaml`](provisioning/dashboards/dashboards.yaml) | Loads every JSON file in `dashboards/`, re-read every 10 seconds |
| [`dashboards/opentelemetry-overview.json`](dashboards/opentelemetry-overview.json) | **OpenTelemetry Overview**: request rate and duration, active requests, recent traces, and logs of `fastapi-example` |
| [`dashboards/emulator-metrics.json`](dashboards/emulator-metrics.json) | **Emulator Metrics**: Qdrant, Elasticsearch and PostgreSQL panels |

## Change a dashboard or data source

- **Add a dashboard:** put its JSON file in `dashboards/`. Grafana picks it up
  within 10 seconds.
- **Keep a change made in the UI:** provisioned items are editable, but the
  files are the source. Copy the dashboard's JSON (Dashboard settings, JSON
  Model) into its file in `dashboards/`.
- **Change a data source:** edit `datasources.yaml`, then restart Grafana.
