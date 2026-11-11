# Emulator Suite

Local emulators for GCP and data services, run with Podman Compose. The root
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

Lite is the default so the Podman machine stays light.
`just emu-start` and `just emu-start-full` first delete all volumes, then build
and wait for readiness. `just emu-clean` deletes the volumes only.

The emulators do not need production credentials, but Google SDKs may still
read ADC. The auth check catches expired tokens and account mismatches early.

SaaS API emulators (GitHub, Stripe, Slack, ...) run separately with
`just emu-api`; see [`emulate/README.md`](emulate/README.md).

## Image-local health checks

Spanner and pgAdapter build the `spanner` and `pgadapter` targets from
[`healthcheck/Dockerfile`](healthcheck/Dockerfile), with only production probe
sources in the build context. Spanner keeps upstream `1.5.57` for primary-key
correctness and adds a static Go TCP connect/close probe with a two-second
connection deadline, called directly without a shell. This is only TCP
readiness on `127.0.0.1:9010`, not a gRPC or SQL check. pgAdapter keeps its
upstream image reference and installs the real upstream `pg_isready` through
`postgresql-client --no-install-recommends`; package installation or executable
verification failure stops the image build. Both targets inherit the upstream
runtime configuration. The Go builder uses `1.27.3`; the floating pgAdapter
reference and OS packages are not reproducibility pins.

Compose uses local output tags and `pull_policy: build`. With podman-compose
1.6, missing outputs build, but an ordinary cached shared-stack start does not
guarantee a rebuild. Isolated verification uses `up --build`. Static contracts,
loopback probe tests and `just healthcheck-build` (four CGO-disabled targets)
do not prove image package availability, ABI compatibility, native health or
SQL behavior. Fresh isolated image builds, inherited-config inspection, positive
and negative health checks, and the original DB/e2e tests remain required.

## Services

All services use project ID `test-project`. Ports bind to `127.0.0.1`; each
host port has an override variable in [`compose.yaml`](compose.yaml) (for
example `POSTGRES_PORT`).

| Service | Compose service | Group | Host ports |
| --- | --- | --- | --- |
| Firebase UI / Auth / Firestore | `firebase-emulator` | lite | 4000 / 9099 / 8080 |
| Firebase Storage / Pub/Sub | `firebase-emulator` | lite | 9199 / 9399 |
| Spanner | `spanner-emulator` | lite | 9010 (gRPC), 9020 (REST) |
| pgAdapter (Spanner, PostgreSQL protocol) | `pgadapter` | lite | 55432 |
| PostgreSQL 18 | `postgres` | lite | 5433 |
| Bigtable | `bigtable-emulator` | `bigtable` | 8086 (gRPC) |
| Elasticsearch | `elasticsearch` | `search` | 9200, 9300 |
| Neo4j | `neo4j` | `graph` | 7474 (HTTP), 7687 (Bolt) |
| Qdrant | `qdrant` | `vector` | 6333 (REST), 6334 (gRPC) |
| MLflow | `mlflow` | `ml` | 5252 |
| A2A Inspector / MCP Inspector | `a2a-inspector`, `mcp-inspector` | `inspect` | 8081 / 6274 (UI), 6277 (proxy) |

The stack does not provide the Firebase Functions, Eventarc, or Tasks
emulators. firebase-tools starts them only when Functions or Extensions are
configured, and [`firebase/firebase.json`](firebase/firebase.json) configures
neither; its `eventarc` and `tasks` entries only set ports. So ports 9299 and
9499 are published, but nothing answers on them.
[`tests/test_firebase_emulators_running.py`](tests/test_firebase_emulators_running.py)
asks the running emulator which emulators it started.

The `full` group holds every service above. The `cli` group holds the
interactive CLIs (see below).

Logins:

- pgAdapter: user `user`, database `test-instance`, no password.
- PostgreSQL: user `postgres`, password `password`, database `postgres`.
- Neo4j: `neo4j` / `password`.

### Connecting

- From the host: copy [`.env.local.example`](.env.local.example) to
  `.env.local` and `source` it. It sets `*_EMULATOR_HOST` and the project IDs.
- From another container: the services join the Podman network
  `shared-otel-net` (`scripts/start-services.sh` creates it; the telemetry
  stack shares it). Use the compose service name and the container port, for
  example `firebase-emulator:8080`, `spanner-emulator:9010`, `pgadapter:5432`,
  `postgres:5432`, `mlflow:5000`. To send OpenTelemetry data, use
  `http://lgtm:4317` (see [`../telemetry/README.md`](../telemetry/README.md)).
- In the A2A or MCP Inspector UI, `localhost` means the inspector container.
  Use `host.containers.internal` to reach a server on the host.
- Open the MCP Inspector with its session token: read it from
  `podman logs mcp-inspector`, then open
  `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>`. The `0.0.0.0` URL in
  the log does not work in a browser. If you changed
  `MCP_INSPECTOR_PROXY_PORT`, add `&MCP_PROXY_PORT=<port>` to the URL.

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
- Debug a service with `PODMAN_COMPOSE_PROVIDER=podman-compose podman compose --in-pod=false logs -f <service>` or
  `PODMAN_COMPOSE_PROVIDER=podman-compose podman compose --in-pod=false exec <service> ...`, run from `emulator/`.

## Data

- Firebase imports `firebase/data/` on start and exports to it on exit.
- MLflow keeps its database and artifacts in `mlflow-data/`.
- The other services use named Podman volumes.
- PostgreSQL ships `pgvector` and `postgis`.
  [`postgres/docker-entrypoint-initdb.d/01-extensions.sql`](postgres/docker-entrypoint-initdb.d/01-extensions.sql)
  enables them only when the volume is first created. On an older volume, run
  `CREATE EXTENSION` yourself or delete the volume with `just emu-clean`.

## Interactive CLIs

Each data service has a small Go REPL behind the `cli` profile. Run it from
`emulator/` while its service is up:

```bash
PODMAN_COMPOSE_PROVIDER=podman-compose podman compose --in-pod=false --profile cli run --rm pgadapter-cli
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

Podman CLI and server must both be 5 or newer. The Python `docker` package is
only a compatibility API client. `tests.utils.helpers.podman_client()` resolves
an explicit local `CONTAINER_HOST` or the selected Podman connection, ignores
`DOCKER_HOST`, and checks the server's `Podman Engine` component. It never starts
a machine or falls back to Docker/TCP. Windows uses the selected machine's named
pipe; its SDK dependency `pywin32` is already in the frozen lock.

### Isolated required tests

Run from a tracked checkout after integrating new support files into git. No
untracked files, `.git`, live Firebase data, or local `.env` files enter the
snapshot. The `prepare` operation does not contact an engine. It creates a new
manifest and refuses to overwrite an existing one. All source ancestors and tracked
components are validated before copying; symlinks, junctions/reparse points,
nonregular files and reserved/Git paths fail closed. Gitlinks are omitted; regular
files retain current working/staged bytes and modes, not original index blobs.
Descriptor no-follow traversal and identity checks are used where supported, with
portable validation elsewhere; this is not a malicious concurrent-writer guarantee.

From `emulator/`:

```bash
export DOTFILES_PODMAN_RUN_MANIFEST="$(pwd)/../podman-run.json"
export DOTFILES_E2E_REQUIRED=1
uv run --frozen python -m tests.utils.isolation prepare \
  --source .. --manifest "$DOTFILES_PODMAN_RUN_MANIFEST" \
  --services firebase-emulator,spanner-emulator,pgadapter,postgres --telemetry
trap 'uv run --frozen python -m tests.utils.isolation cleanup --manifest "$DOTFILES_PODMAN_RUN_MANIFEST"' EXIT
uv run --frozen python -m tests.utils.isolation start --manifest "$DOTFILES_PODMAN_RUN_MANIFEST"
uv run --frozen python -m tests.utils.isolation wait --manifest "$DOTFILES_PODMAN_RUN_MANIFEST"
uv run --frozen pytest tests/e2e -v -m e2e -ra
uv run --frozen pytest tests/test_postgres18_features.py tests/test_postgres18_emulator.py -v
```

`--services` takes Compose service names and includes their dependencies.
`--telemetry` also selects every telemetry service; omit it for DB-only runs.
Tests for deliberately unselected profiles may skip. Connection, build,
container execution, required network and selected-service failures do not skip.
Existing backend feature-probe skips are not claims of feature support.
Build/run fixtures use the immutable ID from this run's build, not an old tag.

The manifest maps canonical container names, host ports, snapshot/engine bind
paths, selected services, one shared run network, and exact owned resource IDs.
Startup, wait, SDK lookups, DB connections and HTTP endpoints use that mapping.
PostgreSQL host, allocated port, user, password and database come from the selected
canonical Compose service; conflicting inherited `POSTGRES_*` settings fail before
connecting. MLflow, pgAdapter and PostgreSQL probes accept only their own canonical
or allocated numeric port, never another service's mapping. Unset conflicting local
settings before required tests. These bounded consumers do not audit every client
library's implicit configuration.
Every fixed name, named volume and published port in both Compose files is
remapped; writable binds use fresh snapshot data. All ports remain loopback.
Port reservations are released before startup, so an external allocation race
fails startup rather than removing whoever acquired the port.

Nested execution requires **both** `DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1`
and `LOCAL_WORKSPACE_FOLDER` pointing to the disposable checkout in the engine's
Unix namespace. The snapshot is then placed inside that checkout and bind paths
are translated through it. A real developer checkout is not a valid writable
mount. Native Windows isolation also needs this explicit engine-visible mapping;
SDK named-pipe support alone does not establish filesystem sharing.

`start-services.sh`, `wait-for-services.sh`, `stop-services.sh` and
`check-status.sh` use the manifest when its environment variable is present.
The shared prebuild/export/verification helpers refuse isolated mode; use this
lifecycle and the manifest-aware DB tests instead. For status or logs:

```bash
uv run --frozen python -m tests.utils.isolation status --manifest "$DOTFILES_PODMAN_RUN_MANIFEST"
uv run --frozen python -m tests.utils.isolation logs --manifest "$DOTFILES_PODMAN_RUN_MANIFEST" --service postgres-18
```

CI must run `cleanup` in an always-step if the manifest exists, including after
startup/test failure. It discovers partial resources by the unique run label,
then rechecks each exact ID and ownership before removal. It never removes by
port or runs shared Compose down/prune. Startup exceptions and SIGINT/SIGTERM
attempt cleanup. SIGKILL, engine failure or interrupted cleanup can leave owned
resources: rerun cleanup with the same manifest and selected connection.
Before any removal, cleanup validates native dependency metadata for surviving
owned full container IDs at that same endpoint, then removes owned dependents
before their parents. Missing/malformed metadata or an owned cycle blocks removal
and later resource cleanup. Each removal freshly checks the exact ID and run label;
only SDK NotFound proves absence. External dependencies never authorize deletion,
and foreign-dependent engine errors propagate without recursive removal or retries.
Build tags are checked absent and journaled before creation. Compose and helper
builds label the actual image with the run ID. Persistent `creations` intents cover
helper images/containers, the run network and Compose (including its volumes).
Authorization is journaled before creation I/O, outside the long-running engine
call. Only a checked positive image/container/network receipt or positive Compose
completion finishes an intent. Application wait/log failures after a container
receipt do not reopen creation; transport errors/nonzero exits are not termination
proof, even if the tag is absent or later observed as owned.

Cleanup atomically closes authorization before discovery. Every subsequent creator
is rejected: prepare a **new manifest** for another run. If any intent was unresolved
at closing, **that cleanup invocation fails incomplete**, even if its producer
positively completes before cleanup returns. Late receipts preserve the closing
barrier and unrelated journal entries; only a later cleanup with fresh discovery
can succeed. Unknown creation stays incomplete without positive producer proof;
there is no automatic adoption/cancellation. Existing partial owned resources may
still be removed. Retain the snapshot, manifest and lock for recovery. Older
image journals without creation intents cannot establish completion; prepare a
fresh run rather than starting an old manifest.

Bare absolute Unix socket paths and local `unix:///path` values share one canonical
binding across discovery, forwarding and persisted endpoints. Controls, nonlocal
URIs and query/fragment/userinfo variants fail before API client creation. Windows
named pipes remain separate; CLI and Podman Engine component versions must still
be >=5. There is no socket fallback or automatic startup.

After owned containers are removed,
cleanup rechecks the exact tag, immutable image ID and run label, then runs only
`podman untag IMAGE_ID TAG` against the manifest endpoint. Foreign aliases,
references, image IDs, layers and build caches are retained; no image removal or
pruning is performed. Ambiguous observations/failed queries retain recovery records
and fail with diagnostics. All manifest writers lock a stable `.lock` file, read
latest state inside the lock, and atomically replace via a unique adjacent temporary
file. Keep the manifest and lock for recovery; do not unlink a live lock file.
Snapshots remain for diagnosis. SIGKILL or engine failure can still leave resources
or build work; tag recovery is not a guarantee of cache reclamation. `wait` verifies
that all selected containers, including telemetry, attach to the same owned run
network, not `shared-otel-net`.

Hermetic support checks (no engine):

```bash
uv run --frozen pytest tests/test_podman_support.py tests/test_podman_isolation.py tests/test_podman_remediation.py tests/test_a2a_inspector_build.py -q
```

### Ordinary local tests

```bash
just emu-test        # all tests
just emu-test-fast   # skip e2e
just emu-test-e2e    # e2e only
```

Firestore runs with fully open security rules
([`firebase/firestore.rules`](firebase/firestore.rules)) so the tests stay
simple. Never use them in production. Optional local probes may skip.

CI runs [`.github/workflows/test-emulators.yaml`](../.github/workflows/test-emulators.yaml)
when files under `emulator/` change (Markdown excluded). `just ci-emu` runs a
local equivalent.
