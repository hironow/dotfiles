# Testing

Read this when writing or placing a test, or whenever you're about to reach for a
mock. The TDD *cycle* is in docs/agents/tdd-workflow.md.

## Where tests live

| dir                  | purpose                                              |
| -------------------- | ---------------------------------------------------- |
| `tests/unit/`        | isolated component tests                             |
| `tests/integration/` | component-interaction tests                          |
| `tests/e2e/`         | full-system tests with **real** dependencies         |
| `tests/runn/`        | scenario tests (`*.yaml`) — API/CLI/agent workflows  |
| `tests/utils/`       | shared helpers (the only importable test location)   |

## Mock policy by test type

- **Unit** — minimize mocks; prefer real code. Mock only external dependencies
  impractical to use in a test. No oversized/complex mocks.
- **Integration** — minimal mocks for *external services only*; prefer test
  containers or local instances.
- **e2e** — **mocks are strictly prohibited.** All dependencies real (DB,
  services, filesystem, network). If a real dependency can't be used, the test
  is not e2e — move it to integration. This is enforced by a Semgrep rule
  (see docs/agents/semgrep.md), not just convention.

## Unit test rules

- Structure as **given / when / then**.
- No try/except inside tests. Keep flat; avoid deep nesting.
- Function-based over class-based.
- Import only from `tests/utils/`.
- Real code over large mocks.

## e2e test rules

Principles: test as a user experiences it; all deps real; deterministic and
repeatable; each test independent. Prohibited: mocks, stubs, fakes,
in-memory replacements, patching/monkey-patching. Required: real DB connections,
real external calls, real filesystem, real network.

Use a dedicated test environment with real services; clean up test data after
each test/session; document setup in `tests/e2e/README.md`.

### Parameterize for coverage

```python
@pytest.mark.parametrize(
    "input_data,expected_status,expected_result",
    [
        pytest.param({"valid": "data"}, 200, {"success": True}, id="valid-input-succeeds"),
        pytest.param({}, 400, {"error": "missing fields"}, id="empty-input-fails"),
        pytest.param({"invalid": "schema"}, 422, {"error": "validation"}, id="invalid-schema-fails"),
    ],
)
def test_api_endpoint(input_data, expected_status, expected_result) -> None:
    # given
    client = create_real_client()
    # when
    response = client.post("/api/endpoint", json=input_data)
    # then
    assert response.status_code == expected_status
    assert response.json() == expected_result
```

## runn scenario tests (`tests/runn/`)

`runn` is a YAML-driven scenario runner for API/CLI testing.

- Files: `tests/runn/*.yaml` and `tests/runn/vars/*.yaml` (never `.yml`).
- Concepts: *runbook* (the YAML scenario), *step* (one HTTP/command action),
  *vars* (values passed between steps).
- Scenarios are realistic; they don't need unit/integration-level coverage.
- A2A protocol scenarios comply with JSON-RPC 2.0.
- Describe steps from the **agent's perspective**:
  - good: `Agent requests task delegation`
  - bad:  `POST to /jsonrpc endpoint`
