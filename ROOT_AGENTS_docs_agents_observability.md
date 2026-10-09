# Observability (OpenTelemetry)

Read this when you add a new service or binary, or any telemetry.

Every service sends telemetry through OpenTelemetry. For local development, use
the shared dotfiles telemetry stack (otel-collector → Tempo/Grafana). A Jaeger
per project is the fallback when you need isolation. Each project picks its
production backend in an ADR.

## Scope

In scope: distributed tracing (traces and spans), structured logs that carry
`trace_id`/`span_id`, and metrics over OTLP where they apply.
Out of scope: vendor SDKs that are not OTel. Use OTel with an exporter instead.

## Instrumentation rules

- Every service or binary starts an OTel `TracerProvider` at startup.
- Export over **OTLP**: gRPC first (`:4317`), HTTP as the fallback (`:4318`).
- Read the endpoint from the standard `OTEL_EXPORTER_OTLP_ENDPOINT` env var.
  Never hard-code it, and above all never hard-code a production endpoint.
- Set `OTEL_SERVICE_NAME` to the tool or module name (`sightjack`, `paintress`,
  `amadeus`, `phonewave`, `dominator`).
- Propagate W3C Trace Context across process boundaries (the SDK default).
- Never put PII or secrets in span attributes. Scrub them before export.

## Minimum span coverage

- Every inbound RPC/HTTP handler → a root span.
- Every outbound RPC/HTTP client call → a child span.
- Every message-bus enqueue or dequeue (including D-Mail Protocol inbox/outbox
  writes) → a span with `messaging.*` attributes.
- Every LLM call (Anthropic, Gemini, …) → a span with `gen_ai.*` attributes
  (model, input tokens, output tokens, latency).

## Python setup

```sh
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
# plus opentelemetry-instrumentation-* per framework: fastapi, httpx, sqlalchemy, …
```

## Go setup

```
go.opentelemetry.io/otel
go.opentelemetry.io/otel/sdk
go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc
```

## Local telemetry

With either option below, apps set
`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` and
`OTEL_SERVICE_NAME=<module>`.

**First choice: the shared stack (run it from the dotfiles repo).**

```sh
just tel-up     # otel-collector (OTLP :4317 gRPC / :4318 HTTP) -> Tempo + Grafana
just tel-down   # stop it
# UI: Grafana at http://localhost:3010 (https://grafana.localhost via portless)
```

You need no telemetry services in each repo. Point apps at the shared
collector.

**Fallback: a Jaeger per project (from the agent-baseline `justfile`)**, for
fully isolated work. `just trace-up` runs Jaeger all-in-one
(`jaegertracing/all-in-one`, `COLLECTOR_OTLP_ENABLED=true`; UI `:16686`,
OTLP `:4317`/`:4318`) from the repo's `compose.yaml`. `just trace-down` stops
it. `just trace-view` opens the UI.

Never run both at once. They bind the same OTLP host ports (`4317`/`4318`), and
that kind of collision has crashed the local Docker VM before. Prefer the
shared stack.

## Production

Each project decides its production exporter target and records it in an ADR
(for example Cloud Trace, Grafana Tempo, Honeycomb). Always reach it through
`OTEL_EXPORTER_OTLP_ENDPOINT`.
