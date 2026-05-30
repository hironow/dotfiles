# Emulator Suite

Local, reproducible emulator stack for app development and testing.

Includes Firebase (Auth / Firestore / Storage / Pub/Sub / Eventarc / Tasks),
Spanner (+ pgAdapter), Neo4j, Elasticsearch, Qdrant, A2A Inspector, and MCP
Inspector. Handy Go-based CLIs and just tasks make day‑to‑day work fast and
predictable.

## Table of Contents

- Quick Start
- Services Overview
- Developer Commands
- Testing
- Configuration
- Access
- Data & Persistence
- CLI Tools (details)
- Troubleshooting
- CI

## Quick Start

Pre-flight (recommended)

```bash
# Validate gcloud user login + ADC and common misconfigurations
just emu-gcloud-auth-check
# or: bash scripts/check-gcloud-auth.sh --details --strict --verbose
```

Note: The Firebase emulator does not need production credentials, but Google SDKs and tools may still read ADC. Running the pre‑flight helps catch expired tokens, missing files, or account mismatches before you start.

Start emulators (recommended)

```bash
just emu-start
```

Stop emulators (recommended)

```bash
just emu-stop
```

Or use Docker Compose directly

```bash
docker compose up -d
# ... later
docker compose down
```

## Services Overview

All services run on the `emulator-network`. Defaults are shown; you can change
ports via `.env.local`.

| Service        | Container            | Ports (host → container)                 | Health | CLI |
|----------------|----------------------|------------------------------------------|--------|-----|
| Bigtable       | `bigtable-emulator`  | 8086 → 8086 (gRPC)                       | TCP    | ✓   |
| Firebase UI    | `firebase-emulator`  | 4000 → 4000                              | HTTP   | –   |
| Firestore      | `firebase-emulator`  | 8080 → 8080                              | TCP    | –   |
| Auth           | `firebase-emulator`  | 9099 → 9099                              | TCP    | –   |
| Pub/Sub        | `firebase-emulator`  | 9399 → 9399                              | HTTP   | –   |
| Storage        | `firebase-emulator`  | 9199 → 9199                              | HTTP   | –   |
| Eventarc       | `firebase-emulator`  | 9299 → 9299                              | HTTP   | –   |
| Tasks          | `firebase-emulator`  | 9499 → 9499                              | HTTP   | –   |
| Spanner gRPC   | `spanner-emulator`   | 9010 → 9010                              | TCP    | –   |
| Spanner REST   | `spanner-emulator`   | 9020 → 9020                              | TCP    | –   |
| pgAdapter      | `pgadapter-emulator` | 55432 → 5432 (PostgreSQL)                | TCP    | ✓   |
| Neo4j          | `neo4j-emulator`     | 7474 → 7474 (HTTP), 7687 → 7687 (Bolt)   | HTTP   | ✓   |
| Elasticsearch  | `elasticsearch-emulator` | 9200 → 9200 (REST), 9300 → 9300     | HTTP   | ✓   |
| Qdrant         | `qdrant-emulator`    | 6333 → 6333 (REST), 6334 → 6334 (gRPC)   | HTTP   | ✓   |
| A2A Inspector  | `a2a-inspector`      | 8081 → 8080                              | HTTP   | –   |
| MCP Inspector  | `mcp-inspector`      | 6274 → 6274                              | HTTP   | –   |
| MLflow         | `mlflow-server`      | 5252 → 5000                              | HTTP   | –   |
| PostgreSQL     | `postgres-18`        | 5433 → 5432 (PostgreSQL)                 | TCP    | ✓   |
| ES Exporter    | `elasticsearch-exporter` | 9114 → 9114 (Prometheus)            | HTTP   | –   |
| PG Exporter    | `postgres-exporter`  | 9187 → 9187 (Prometheus)                 | HTTP   | –   |

> Note: Set `A2A_INSPECTOR_REPO=<git-url>` and/or `A2A_INSPECTOR_REF=<git-ref>` before `just emu-start` to pin the upstream inspector checkout. The image builds via the local `a2a-inspector/Dockerfile`, which fetches the repository and runs on Python 3.12 to satisfy its runtime requirement.

> Note: Set `MCP_INSPECTOR_REPO=<git-url>` and/or `MCP_INSPECTOR_REF=<git-ref>` before `just emu-start` to pin the upstream MCP Inspector checkout. The image builds via the local `mcp-inspector/Dockerfile`, which fetches the repository and runs on Node.js 24.

CLI availability (✓) means a matching Go-based REPL is included and runnable
via Docker Compose profiles.

### Prometheus Exporters

The following Prometheus exporters are included for telemetry integration:

| Exporter | Target Service | Metrics Endpoint | Notes |
|----------|---------------|------------------|-------|
| `elasticsearch-exporter` | Elasticsearch | `:9114/metrics` | Cluster health, nodes, JVM, indices |
| `postgres-exporter` | PostgreSQL 18 | `:9187/metrics` | Connections, DB size, QPS, cache hits |

These exporters are scraped by the OTEL Collector in the `telemetry` stack via the shared `shared-otel-net` Docker network. Metrics are visualized in the Grafana "Emulator Metrics" dashboard.

**Native metrics support:**

- **Qdrant**: Native `/metrics` endpoint on port 6333
- **Neo4j**: Prometheus metrics require Enterprise Edition (Community Edition does not support this feature)

## Developer Commands

All recipes live in the repo-root `justfile` under the `Emulator` group
(run `just --list`):

- `just emu-start` / `just emu-stop` — start (clean+prebuild+up+wait) / stop emulators
- `just emu-up` / `just emu-check` / `just emu-wait` — start detached / status / wait for readiness
- `just emu-test` / `just emu-test-fast` / `just emu-test-e2e` — pytest (all / non-e2e / e2e)
- `just emu-lint` / `just emu-fmt` — ruff + semgrep + markdownlint / formatters
- `just emu-pg-verify` — PostgreSQL 18 verification
- `just emu-gcloud-auth-check` — pre-flight gcloud auth/ADC check (strict + details)

## Testing

Run all tests

```bash
just emu-test
```

Coverage highlights

- Firestore: Create/Get via REST (runs with emulator-specific permissive rules)
- Auth: SignUp / SignInWithPassword
- Storage: Upload/Download (continues even when the bucket-creation API is unimplemented)
- Pub/Sub: Topic / Subscription / Publish / Pull / Ack via REST
- Eventarc: Port connectivity smoke test
- Spanner / pgAdapter: Container liveness and TCP port checks
- Neo4j / Elasticsearch / Qdrant: Health verification

Test groups

- Smoke: CLI help/info/exit sanity checks
- CRUD: End‑to‑end create/read flows per CLI (with cleanup)
- Features: Aggregations, relationships, filtered vector search
- Negative: pgAdapter/Spanner incompat tests (e.g., missing PK, sequence)

About skipped tests (expected)

- Pub/Sub REST: Some emulator builds or environments may return 500s because of HTTP/2 requirements or unstable REST responses.
    - Tests use aiohttp and skip instead of fail when responses are flaky.
    - On environments where the emulator mandates HTTP/2, the test skips automatically.
- Cloud Tasks REST: Frequently unimplemented; we detect that ahead of time and skip.

Note: Firestore security rules are switched to fully permissive mode for the local emulator to simplify tests. Never use this configuration in production.

## Configuration

All emulators use the same project ID: `test-project`.

Copy example envs and/or export in your shell.

```bash
# Core project configuration
export CLOUDSDK_CORE_PROJECT=test-project
export GOOGLE_CLOUD_PROJECT=test-project
export FIREBASE_PROJECT_ID=test-project

# Firebase Emulator hosts
export FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIREBASE_STORAGE_EMULATOR_HOST=localhost:9199
export PUBSUB_EMULATOR_HOST=localhost:9399

# Spanner Emulator host
export SPANNER_EMULATOR_HOST=localhost:9010
export BIGTABLE_EMULATOR_HOST=localhost:8086
export POSTGRES_PORT=5433
export PGADAPTER_PORT=55432

# Authentication (empty for emulators)
export GOOGLE_APPLICATION_CREDENTIALS=""

# Optional
export CLOUD_TASKS_EMULATOR_HOST=localhost:9090
export EVENTARC_EMULATOR=localhost:9299
export JAVA_TOOL_OPTIONS="-Xmx4g"
export CLOUDSDK_SURVEY_DISABLE_PROMPTS=1
```

Docker-to-Docker networking

```bash
export FIREBASE_AUTH_EMULATOR_HOST=firebase:9099
export FIRESTORE_EMULATOR_HOST=firebase:8080
export FIREBASE_STORAGE_EMULATOR_HOST=firebase:9199
export PUBSUB_EMULATOR_HOST=firebase:9399
export SPANNER_EMULATOR_HOST=spanner:9010
export BIGTABLE_EMULATOR_HOST=bigtable-emulator:8086

# MLflow client (inside another container)
export MLFLOW_TRACKING_URI=http://mlflow:5000

Local host client (MLflow)

```bash
export MLFLOW_TRACKING_URI=http://localhost:5252
```

**macOS Port Conflicts**

- On macOS, Control Center (AirPlay) commonly binds ports `5000` and `7000`.
- Avoid exposing emulator services on these host ports. This repo uses `5252` for MLflow by default.

## Access

- pgAdapter (PostgreSQL): host `localhost`, port `55432`, user `user`, db `test-instance`
- Bigtable: gRPC `localhost:8086`
- Neo4j: Bolt `localhost:7687`, HTTP `localhost:7474` (neo4j / password)
- Elasticsearch: REST `localhost:9200`
- Qdrant: REST `localhost:6333`
- A2A Inspector: `http://localhost:8081`
- MCP Inspector: `http://localhost:6274`
- MLflow UI: `http://localhost:5252`
- PostgreSQL: host `localhost`, port `5433`, user `postgres`, db `postgres`

Note (A2A Inspector): Entering `localhost` in the web UI resolves inside the container; use `host.docker.internal` to reach the host.

## Data & Persistence

- Firebase data persists under `firebase/data/`.
- Firebase emulator exports on exit automatically (export-on-exit). `just emu-stop` simply stops containers.
- MLflow experiment data (backend + artifacts) persists under `mlflow-data/`.

## CLI Tools (details)

Docs

- [Firebase Emulator](firebase/README.md)
- [pgAdapter CLI](pgadapter-cli/README.md)
- [Neo4j CLI](neo4j-cli/README.md)
- [Elasticsearch CLI](elasticsearch-cli/README.md)
- [Qdrant CLI](qdrant-cli/README.md)
- [Bigtable CLI](bigtable-cli/README.md)

PostgreSQL CLI

```bash
docker compose --profile cli run --rm postgres-cli
```

PostgreSQL 18 verification

```bash
just emu-pg-verify
```

Run with Docker Compose profiles. Examples:

pgAdapter CLI

```bash
docker compose --profile cli run --rm pgadapter-cli
```

Neo4j CLI

```bash
docker compose --profile cli run --rm neo4j-cli
```

Bigtable CLI

```bash
docker compose --profile cli run --rm bigtable-cli
```

Elasticsearch CLI

```bash
docker compose --profile cli run --rm elasticsearch-cli
```

Qdrant CLI

```bash
docker compose --profile cli run --rm qdrant-cli
```

All CLIs support multi‑line input and print tabular results for readability.

Apple Silicon (arm64)

- Bigtable emulator image is amd64-only; the compose service sets `platform: linux/amd64` to run via emulation.
- Performance impact is usually small for local testing. If you prefer native arm64, consider running the emulator directly on host via `gcloud`.

## Troubleshooting

Health checks

```bash
just emu-check
```

Tips

- Firebase UI may take 30–60s to fully start.
- Firestore root endpoint does not return 200; use port listen checks and UI.
- Inspect logs: `docker compose logs -f <service>`
- Test from inside container: `docker compose exec <service> curl ...`
- Verify messages like "ready", "started", or "listening" in logs.

## CI

GitHub Actions workflow `.github/workflows/test-emulators.yaml` (repo root,
`paths:` scoped to `emulator/**`, `working-directory: emulator`):

- Installs dependencies via `uv sync --all-extras --frozen` (lockfile に準拠)
- Runs tests via `uv run pytest`

Run the same suite locally with `just ci-emu` (lint + start + fast + e2e).

## pgAdapter / Spanner Dialect Differences

When using pgAdapter (PostgreSQL protocol) on top of Spanner, prefer PostgreSQL
type names and be aware of some limitations. Quick mapping:

| Concept                     | Spanner (GoogleSQL)         | PostgreSQL (via pgAdapter) |
|----------------------------|-----------------------------|-----------------------------|
| Integer                    | `INT64`                     | `BIGINT`                    |
| String (fixed length)      | `STRING(n)`                 | `VARCHAR(n)`                |
| String (unbounded)         | `STRING`                    | `TEXT`                      |
| Floating point             | `FLOAT64`                   | `DOUBLE PRECISION`          |
| Exact decimal              | `NUMERIC`                   | `NUMERIC`                   |
| Timestamp                  | `TIMESTAMP`                 | `TIMESTAMPTZ`               |
| Primary key                | `PRIMARY KEY (id)`          | `id BIGINT PRIMARY KEY` or table-level PK |

Notes

- Every table must have a PRIMARY KEY (Spanner requirement).
- `SERIAL` / `SEQUENCE` are generally unsupported.
- Some PostgreSQL features may be limited compared to stock PostgreSQL.
- Keep DDL simple (explicit PK, basic types) for best compatibility.

## PostgreSQL 18

Highlights (stock PostgreSQL, not pgAdapter):

- Asynchronous I/O for reads improves performance in sequential scan, bitmap heap scan, and VACUUM read paths (benchmarks show up to ~3x on targeted operations)
- `uuidv7()` function to generate time-ordered UUIDs (millisecond timestamp prefix)
- Generated columns: support for virtual generated columns in addition to stored
- OAuth 2.0 authentication support and upgrade-safe statistics retention

How to use

- Start with the rest of the suite: `just emu-start`
- CLI (Docker profile): `docker compose --profile cli run --rm postgres-cli`
- Host access: `psql -h localhost -p ${POSTGRES_PORT:-5433} -U postgres -d postgres`
- Quick verification of version, `uuidv7()`, and generated columns: `just emu-pg-verify`

Notes

- This PostgreSQL 18 service is independent from Spanner/pgAdapter. Use it when you need exact PostgreSQL behavior or to try 18-specific features.
- Inside Docker, connect to `postgres:5432`. From the host, the default mapped port is `5433` (change via `POSTGRES_PORT`).

Extensions

- Preinstalled: `pgvector`, `postgis`
- Auto-enabled on first initialization via `postgres/docker-entrypoint-initdb.d/01-extensions.sql`
- If you created the data volume before this change, either run `CREATE EXTENSION` manually inside the DB or remove the `postgres_data` volume to trigger the init script
