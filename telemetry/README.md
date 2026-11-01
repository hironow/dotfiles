# OpenTelemetry Visualization Suite

A local Docker stack that collects OpenTelemetry traces, metrics and logs and
shows them in Grafana. It also scrapes metrics from the `emulator` stack.
[`examples/`](examples/README.md) holds a FastAPI app that sends sample data.

## Quick start

From the repo root:

```bash
just tel-up      # create the shared-otel-net network if missing, then docker compose up -d
just tel-check   # docker compose ps
just tel-logs    # follow logs (optionally: just tel-logs grafana)
just tel-down
```

Open Grafana at <http://localhost:3010> (admin/admin). To send sample data, run
the example app: see [`examples/README.md`](examples/README.md).

## Components and host ports

[`compose.yaml`](compose.yaml) is the source for images and ports. Every port is
bound to `127.0.0.1`.

| Service | Host port | Purpose |
| --- | --- | --- |
| Grafana | 3010 | Web UI (container port 3000) |
| Prometheus | 9091 | Metrics store (container port 9090) |
| Tempo | 3200, 14268 | Trace store HTTP API, Jaeger ingest |
| Loki | 3100 | Log store |
| OTel Collector | 4317, 4318 | OTLP gRPC, OTLP HTTP |
| OTel Collector | 8888, 8889 | Collector's own metrics, Prometheus exporter |
| OTel Collector | 13133, 55679 | `health_check`, `zpages` |

For `https://<name>.localhost` aliases of the HTTP UIs, see
[`../docs/portless-urls.md`](../docs/portless-urls.md).

## Data flow

```txt
app            --OTLP-------->  OTel Collector
OTel Collector --scrape------>  emulator exporters
OTel Collector --traces------>  Tempo (tempo:4317)
OTel Collector --logs-------->  Loki (http://loki:3100/otlp)
OTel Collector --metrics----->  :8889  <--scrape--  Prometheus
Tempo          --span metrics->  Prometheus (remote write)
Grafana        --queries----->  Prometheus, Tempo, Loki
```

Each step has one config file:

| Step | File |
| --- | --- |
| Collector receivers, exporters, emulator scrapes | [`config/otel/otel-collector-config.yaml`](config/otel/otel-collector-config.yaml) |
| Prometheus scrapes (collector `:8888` and `:8889`, every 15s) | [`config/prometheus/prometheus.yaml`](config/prometheus/prometheus.yaml) |
| Tempo storage and span-metrics generator | [`config/tempo/tempo-config.yaml`](config/tempo/tempo-config.yaml) |
| Loki storage | [`config/loki/loki-config.yaml`](config/loki/loki-config.yaml) |
| Grafana data sources and dashboards | [`grafana/`](grafana/README.md) |

Services reach each other by service name on the `shared-otel-net` network. Only
the ports above are open to the host. [`docs/architecture-diagram.md`](docs/architecture-diagram.md)
has a Mermaid version of the diagram.

## Emulator metrics

The collector scrapes three `emulator` services every 30s over
`shared-otel-net` and passes the metrics to Prometheus. The **Emulator Metrics**
dashboard shows them.

| Service | Target | Started by |
| --- | --- | --- |
| Qdrant | `qdrant-emulator:6333` | `just emu-up-group vector` |
| Elasticsearch | `elasticsearch-exporter:9114` | `just emu-up-group search` |
| PostgreSQL | `postgres-exporter:9187` | `just emu-up-group exporters` |

`just emu-up-full` starts all three. The default `just emu-up` (lite) starts
none of them, so the dashboard stays empty. Both `just tel-up` and the emulator
start script create `shared-otel-net` when it is missing. To run the stacks
without `just`, create the network first:

```bash
docker network create shared-otel-net
(cd telemetry && docker compose up -d)
```

## No data in Grafana

1. Run `just tel-check` and check that every container is up.
2. Check that the app sends to `localhost:4317` (`OTEL_EXPORTER_OTLP_ENDPOINT`).
3. Wait a few seconds: the collector sends in batches.
