# Local telemetry (grafana/otel-lgtm)

One container, [grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm),
collects OpenTelemetry traces, metrics, logs and profiles and shows them in
Grafana. It bundles the OpenTelemetry Collector, Prometheus, Tempo, Loki,
Pyroscope and Grafana with upstream defaults. dotfiles keeps no config,
dashboards or example app of its own (ADR 0072). Upstream says the image is for
development, demos and tests, not production.

## Quick start

From the repo root:

```bash
just tel-up      # create shared-otel-net if missing, then start lgtm
just tel-check   # show the container
just tel-logs    # follow logs
just tel-down    # stop it (also removes containers an older stack left)
```

Open Grafana at <http://localhost:3000> and log in as `admin` / `admin`.

## Host ports

[`compose.yaml`](compose.yaml) is the source for the image and the ports. Every
port is bound to `127.0.0.1` and uses lgtm's own number.

| Port | Service |
| --- | --- |
| 3000 | Grafana |
| 3200 | Tempo HTTP API |
| 4040 | Pyroscope |
| 4317 | OTLP gRPC |
| 4318 | OTLP HTTP |
| 9090 | Prometheus |

For `https://<name>.localhost` aliases of the HTTP UIs, see
[`../docs/portless-urls.md`](../docs/portless-urls.md).

## Send telemetry

- From the host: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` (gRPC) or
  `http://localhost:4318` (HTTP).
- From a container on the `shared-otel-net` network: `http://lgtm:4317` or
  `http://lgtm:4318`. The emulator stack joins that network too.

## Data and settings

Data lives in the `lgtm-data` named volume (`/data` in the container), so it
survives `just tel-down`. Remove the volume to start empty.

Upstream documents environment variables that change the bundled services
(for example `PROMETHEUS_EXTRA_ARGS` or `ENABLE_LOGS_ALL`); see its README. Keep
the upstream config files: do not mount config files of our own (ADR 0072).
`.env` next to `compose.yaml` is git-ignored, so local values stay untracked.

## Upgrade the image

Dependabot proposes a new tag 7 days after its release
(`.github/dependabot.yaml`). Before merging, check the image's attestation:

```bash
gh attestation verify --repo grafana/docker-otel-lgtm \
  oci://docker.io/grafana/otel-lgtm:<version> \
  --signer-workflow grafana/shared-workflows/.github/workflows/sign-and-attest.yml
```

## Move from the old five-container stack

The old stack ran otel-collector, Tempo, Prometheus, Loki and Grafana. After you
pull this change, run `just tel-down` once: `--remove-orphans` stops the old
containers that still hold ports 4317 and 4318. Then `just tel-up`. The old
volumes stay; remove them when you no longer need their data:

```bash
podman volume rm telemetry_grafana-data telemetry_prometheus-data telemetry_tempo-data
```

## Isolated verification

Use the [emulator test lifecycle](../emulator/README.md#isolated-required-tests)
with `--telemetry`. It renders both canonical Compose files into one tracked-only
disposable snapshot. Both stacks share a unique owned network; container names,
volumes and loopback host ports are isolated. The same run manifest drives
startup, wait, SDK lookups and host endpoints. `wait` checks every selected
container's health and network membership, and
`emulator/tests/e2e/test_telemetry_lgtm_e2e.py` sends one span over OTLP and
reads it back from Tempo. Normal `shared-otel-net` and existing telemetry data
are not touched.

The forced provider is `PODMAN_COMPOSE_PROVIDER=podman-compose`, with
`--in-pod=false`; no extra Pod inventory is created. CI always invokes cleanup
with the same manifest after success, failure or cancellation. Cleanup rechecks
run labels and exact IDs, never port-based deletion or shared-stack teardown.

## No data in Grafana

1. Run `just tel-check` and check that the container is healthy.
2. Check that the app sends to `localhost:4317` (`OTEL_EXPORTER_OTLP_ENDPOINT`).
3. Wait a few seconds: the collector sends in batches.
