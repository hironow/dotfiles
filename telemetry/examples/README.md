# FastAPI OpenTelemetry Example

A FastAPI app that sends traces, metrics and logs to the telemetry stack. It
shows automatic route and httpx instrumentation, custom metrics (counter,
histogram, up-down counter), logs that carry the trace ID, and recorded
exceptions.

## Run it

1. Start the stack from the repo root: `just tel-up`.
2. Start the app from this directory:

   ```bash
   uv sync
   uv run python app.py   # listens on http://localhost:8000
   ```

The app sends OTLP to `OTEL_EXPORTER_OTLP_ENDPOINT`, which defaults to
`localhost:4317`. It reports as service `fastapi-example`.

## Endpoints

| Endpoint | What it does |
| --- | --- |
| `GET /` | Root endpoint |
| `GET /api/users/{user_id}` | Returns a user; `user_id=999` returns 404 |
| `POST /api/orders` | Creates an order |
| `GET /api/external` | Calls `https://httpbin.org/json` (needs the internet) |
| `GET /api/slow` | Slow operation with several child spans |
| `GET /health` | Health check |

Send some traffic:

```bash
curl http://localhost:8000/
curl http://localhost:8000/api/users/123
curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"items": [{"name": "item1", "price": 10}, {"name": "item2", "price": 20}]}'
curl http://localhost:8000/api/slow
```

Then open Grafana at <http://localhost:3010> (admin/admin) and use the
**OpenTelemetry Overview** dashboard.
