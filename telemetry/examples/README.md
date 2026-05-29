# FastAPI OpenTelemetry Example

This example demonstrates a FastAPI application with comprehensive OpenTelemetry instrumentation for traces, metrics, and logs.

## Features

- Distributed tracing with automatic span creation
- Custom metrics (counters, histograms, up-down counters)
- Structured logging with trace correlation
- Automatic instrumentation of FastAPI routes
- HTTP client instrumentation (httpx)
- Error tracking and exception recording

## Running the Application

1. Make sure the Docker Compose stack is running:

   ```bash
   cd ..
   docker compose up -d
   ```

2. Run the FastAPI application:

   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT="localhost:4317"
   uv sync  
   uv run python app.py
   ```

## API Endpoints

- `GET /` - Root endpoint
- `GET /api/users/{user_id}` - Get user by ID (404 if user_id=999)
- `POST /api/orders` - Create a new order
- `GET /api/external` - Call external service (httpbin.org)
- `GET /api/slow` - Simulate slow operation with multiple steps
- `GET /health` - Health check endpoint

## Testing

Send some requests to generate telemetry data:

```bash
# Basic request
curl http://localhost:8000/

# Get user
curl http://localhost:8000/api/users/123

# Create order
curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"items": [{"name": "item1", "price": 10}, {"name": "item2", "price": 20}]}'

# Slow operation
curl http://localhost:8000/api/slow

# External API call
curl http://localhost:8000/api/external
```

## View in Grafana

Open Grafana at <http://localhost:3010> (admin/admin) to view:

- Traces in Tempo
- Metrics in Prometheus
- Logs in Loki
