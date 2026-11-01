# Emulator Suite

Local emulators for GCP and data services, run with Docker Compose. The root
`justfile` drives them (`just --list`, group `Emulator`). The default is a
small "lite" stack; heavier services start only when you ask for them.

## Quick start

```bash
just emu-gcloud-auth-check           # optional: check gcloud login and ADC first
just emu-up                          # lite: firebase + spanner + pgadapter + postgres
just emu-up-group search             # lite + one group (see Services)
just emu-up-only firebase-emulator   # only the named services
just emu-up-full                     # every data service
just emu-check                       # status and endpoints
just emu-stop                        # stop every service, lite and heavy
```

Lite is the default so the Docker VM (OrbStack or podman machine) stays light.
`just emu-start` and `just emu-start-full` first delete all volumes, then build
and wait for readiness. `just emu-clean` deletes the volumes only.

The emulators do not need production credentials, but Google SDKs may still
read ADC. The auth check catches expired tokens and account mismatches early.

SaaS API emulators (GitHub, Stripe, Slack, ...) run separately with
`just emu-api`; see [`emulate/README.md`](emulate/README.md).

## Services

All services use project ID `test-project`. Ports bind to `127.0.0.1`; each
host port has an override variable in [`compose.yaml`](compose.yaml) (for
example `POSTGRES_PORT`).

| Service | Compose service | Group | Host ports |
| --- | --- | --- | --- |
| Firebase UI / Auth / Firestore | `firebase-emulator` | lite | 4000 / 9099 / 8080 |
| Firebase Storage / Pub/Sub | `firebase-emulator` | lite | 9199 / 9399 |
| Firebase Eventarc / Tasks | `firebase-emulator` | lite | 9299 / 9499 |
| Spanner | `spanner-emulator` | lite | 9010 (gRPC), 9020 (REST) |
| pgAdapter (Spanner, PostgreSQL protocol) | `pgadapter` | lite | 55432 |
| PostgreSQL 18 | `postgres` | lite | 5433 |
| Bigtable | `bigtable-emulator` | `bigtable` | 8086 (gRPC) |
| Elasticsearch + exporter | `elasticsearch`, `elasticsearch-exporter` | `search` | 9200, 9300 / 9114 |
| Neo4j | `neo4j` | `graph` | 7474 (HTTP), 7687 (Bolt) |
| Qdrant | `qdrant` | `vector` | 6333 (REST), 6334 (gRPC) |
| MLflow | `mlflow` | `ml` | 5252 |
| A2A Inspector / MCP Inspector | `a2a-inspector`, `mcp-inspector` | `inspect` | 8081 / 6274 |
| PostgreSQL exporter | `postgres-exporter` | `exporters` | 9187 |

The `full` group holds every service above. The `cli` group holds the
interactive CLIs (see below).

Logins:

- pgAdapter: user `user`, database `test-instance`, no password.
- PostgreSQL: user `postgres`, password `password`, database `postgres`.
- Neo4j: `neo4j` / `password`.

### Connecting

- From the host: copy [`.env.local.example`](.env.local.example) to
  `.env.local` and `source` it. It sets `*_EMULATOR_HOST` and the project IDs.
- From another container: the services join the Docker network
  `shared-otel-net` (`scripts/start-services.sh` creates it; the telemetry
  stack shares it). Use the compose service name and the container port, for
  example `firebase-emulator:8080`, `spanner-emulator:9010`, `pgadapter:5432`,
  `postgres:5432`, `mlflow:5000`.
- In the A2A or MCP Inspector UI, `localhost` means the inspector container.
  Use `host.docker.internal` to reach a server on the host.

### Notes

- Bigtable and A2A Inspector images are amd64-only. On Apple Silicon they run
  under emulation (`platform: linux/amd64`).
- On macOS, Control Center (AirPlay) holds ports 5000 and 7000. That is why
  MLflow uses host port 5252.
- The inspectors build from upstream source at a pinned ref. Set
  `A2A_INSPECTOR_REPO` / `A2A_INSPECTOR_REF` or `MCP_INSPECTOR_REPO` /
  `MCP_INSPECTOR_REF` before building to use another checkout. The defaults and
  the reasons for the pins are in [`compose.yaml`](compose.yaml) and each
  inspector's `Dockerfile`.
- Firebase UI can take 30-60 seconds to start. The Firestore root URL does not
  return 200; check the port or the UI instead.
- Debug a service with `docker compose logs -f <service>` or
  `docker compose exec <service> ...`, run from `emulator/`.

## Data

- Firebase imports `firebase/data/` on start and exports to it on exit.
- MLflow keeps its database and artifacts in `mlflow-data/`.
- The other services use named Docker volumes.
- PostgreSQL ships `pgvector` and `postgis`.
  [`postgres/docker-entrypoint-initdb.d/01-extensions.sql`](postgres/docker-entrypoint-initdb.d/01-extensions.sql)
  enables them only when the volume is first created. On an older volume, run
  `CREATE EXTENSION` yourself or delete the volume with `just emu-clean`.

## Metrics

The telemetry stack's OTel Collector scrapes `elasticsearch-exporter:9114`,
`postgres-exporter:9187`, and Qdrant's own `/metrics` on 6333 (see
[`../telemetry/config/otel/otel-collector-config.yaml`](../telemetry/config/otel/otel-collector-config.yaml)).
Grafana shows them on the "Emulator Metrics" dashboard. Neo4j Community
Edition has no Prometheus metrics.

## Interactive CLIs

Each data service has a small Go REPL behind the `cli` profile. Run it from
`emulator/` while its service is up:

```bash
docker compose --profile cli run --rm pgadapter-cli
```

The CLIs are `bigtable-cli`, `elasticsearch-cli`, `neo4j-cli`,
`pgadapter-cli`, `postgres-cli`, and `qdrant-cli`. Type `\h` inside for
commands and examples. Compose sets each CLI's connection variables.

- `bigtable-cli`: run `init` first. It creates the instance and cluster if
  they are missing and is safe to repeat.
- `pgadapter-cli` and `postgres-cli` read the standard libpq variables
  (`PGHOST`, `PGPORT`, ...). From the host, use port 55432 for pgAdapter and
  5433 for PostgreSQL.
- `elasticsearch-cli`: see [its README](elasticsearch-cli/README.md).

## pgAdapter vs PostgreSQL

`pgadapter` speaks the PostgreSQL protocol on top of Spanner. `postgres` is
stock PostgreSQL 18 and does not depend on Spanner. Use `postgres` when you
need exact PostgreSQL behavior. `just emu-pg-verify` checks its version,
`uuidv7()`, and generated columns.

Through pgAdapter, write PostgreSQL type names:

| Spanner (GoogleSQL) | PostgreSQL (via pgAdapter) |
| --- | --- |
| `INT64` | `BIGINT` |
| `STRING(n)` / `STRING` | `VARCHAR(n)` / `TEXT` |
| `FLOAT64` | `DOUBLE PRECISION` |
| `NUMERIC` | `NUMERIC` |
| `TIMESTAMP` | `TIMESTAMPTZ` |

- Every table needs a primary key (`id BIGINT PRIMARY KEY`).
- `SERIAL` and sequences are generally not supported.
- Keep DDL simple: explicit primary key, basic types.

## Tests and CI

```bash
just emu-test        # all tests
just emu-test-fast   # skip e2e
just emu-test-e2e    # e2e only
```

Firestore runs with fully open security rules
([`firebase/firestore.rules`](firebase/firestore.rules)) so the tests stay
simple. Never use them in production. The Cloud Tasks test skips when the
emulator does not implement the REST API.

CI runs [`.github/workflows/test-emulators.yaml`](../.github/workflows/test-emulators.yaml)
when files under `emulator/` change (Markdown excluded). `just ci-emu` runs a
local equivalent.
