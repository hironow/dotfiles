"""The isolated telemetry stack (grafana/otel-lgtm, ADR 0072) works end to end.

The run's `--telemetry` starts telemetry/compose.yaml next to the emulators.
This test sends one span over OTLP/HTTP, finds it in Tempo, and checks that
Grafana answers, all through the run's remapped host ports.
"""

import asyncio
import secrets
import time

import pytest

from tests.utils.helpers import host_endpoint, owned_container


@pytest.mark.asyncio
async def test_lgtm_stores_an_otlp_span_and_serves_grafana(
    http_client, podman_client, ensure_network, require_services
):
    ensure_network()
    require_services(["lgtm"])
    container = owned_container(podman_client, "lgtm")
    container.reload()
    # compose declares the healthcheck; a missing Health block means it was lost.
    health = ((container.attrs or {}).get("State") or {}).get("Health") or {}
    assert health.get("Status") == "healthy", health

    trace_id = secrets.token_hex(16)
    now = time.time_ns()
    span = {
        "traceId": trace_id,
        "spanId": secrets.token_hex(8),
        "name": "dotfiles-e2e",
        "kind": 1,
        "startTimeUnixNano": str(now - 1_000_000),
        "endTimeUnixNano": str(now),
    }
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "e2e"}}
                    ]
                },
                "scopeSpans": [{"spans": [span]}],
            }
        ]
    }
    async with http_client.post(
        host_endpoint("http://localhost:4318/v1/traces"), json=payload
    ) as resp:
        assert resp.status == 200, await resp.text()

    trace_url = host_endpoint(f"http://localhost:3200/api/traces/{trace_id}")
    for _ in range(60):
        async with http_client.get(trace_url) as resp:
            if resp.status == 200:
                break
        await asyncio.sleep(1)
    else:
        pytest.fail(f"Tempo never returned trace {trace_id} (last {resp.status})")

    async with http_client.get(
        host_endpoint("http://localhost:3000/api/health")
    ) as resp:
        assert resp.status == 200, await resp.text()
