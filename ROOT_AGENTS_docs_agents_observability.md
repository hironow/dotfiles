# Observability (OpenTelemetry + Jaeger)

Read this when adding a new service/binary or any telemetry. All services emit
telemetry via OpenTelemetry. Local dev uses Jaeger; production backends are
chosen per project in an ADR.

## Scope

In: distributed tracing (traces + spans), structured logs correlated with
`trace_id`/`span_id`, metrics via OTLP when applicable.
Out: non-OTel vendor SDKs — use OTel with an exporter instead.

## Instrumentation rules

- Every service/binary initializes an OTel `TracerProvider` at startup.
- Exporter is **OTLP** — gRPC preferred (`:4317`), HTTP fallback (`:4318`).
- Endpoint via the standard `OTEL_EXPORTER_OTLP_ENDPOINT` env var — never
  hard-code it (especially not production endpoints).
- `OTEL_SERVICE_NAME` matches the tool/module name (`sightjack`, `paintress`,
  `amadeus`, `phonewave`, `dominator`).
- Propagate W3C Trace Context across process boundaries (SDK default).
- Never put PII or secrets in span attributes; scrub before export.

## Minimum span coverage

- Every inbound RPC/HTTP handler → a root span.
- Every outbound RPC/HTTP client call → a child span.
- Every message-bus enqueue/dequeue (including D-Mail Protocol inbox/outbox
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

## Local Jaeger

`compose.yaml` runs a Jaeger all-in-one (`jaegertracing/all-in-one`,
`COLLECTOR_OTLP_ENABLED=true`; ports `16686` UI / `4317` gRPC / `4318` HTTP).
Apps set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` and
`OTEL_SERVICE_NAME=<module>`.

```sh
just trace-up     # docker compose -f compose.yaml up -d jaeger
just trace-down   # stop it
just trace-view   # open http://localhost:16686
```

## Production

The production exporter target is decided per project and recorded in an ADR
(e.g. Cloud Trace, Grafana Tempo, Honeycomb). Always reach it via
`OTEL_EXPORTER_OTLP_ENDPOINT`.
