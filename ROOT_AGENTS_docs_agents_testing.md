# Testing

Read this when you write or place a test, or when you are about to use a
mock. The TDD *cycle* is in docs/agents/tdd-workflow.md.

## Kinds of tests

The kind of a test depends on what it touches, not on where its file lives.
These instructions do not require a test directory or a test-file layout.

| kind        | what it touches                                       |
| ----------- | ----------------------------------------------------- |
| unit        | one component, isolated                               |
| integration | several components, or one real external service      |
| e2e         | the full system with **real** dependencies only       |
| scenario    | API, CLI, or agent workflows written as `runn` YAML   |

## Mock policy by test kind

- **Unit** — Test the core with plain values; it needs no fake and no mock.
  Test the shell with the fakes in `fake/` (docs/agents/core-shell-ports.md).
  Mock only an external dependency that has no fake and is impractical to use
  in a test. Do not write large or complex mocks.
- **Integration** — Use fakes for external services you are not testing, and as
  few mocks as you can. Prefer test containers or local instances. Run each
  port's contract tests against the real adapter here, with a dedicated test
  account or a local emulator.
- **e2e** — **Mocks are strictly prohibited.** Every dependency is real (DB,
  services, filesystem, network). If you cannot use a real dependency, the test
  is not e2e: move it to integration. The agent-baseline Semgrep rule checks
  this only for Python files under `tests/e2e/` (see docs/agents/semgrep.md).
  Everywhere else, review enforces it.

## Unit test rules

- Structure each test as **given / when / then**.
- Do not put try/except inside tests. Keep tests flat; avoid deep nesting.
- Prefer tests written as functions over classes.
- Use real code, not large mocks.

## e2e test rules

Principles: test what a user experiences; use only real dependencies; make
every run deterministic and repeatable; keep each test independent.

- Prohibited: mocks, stubs, fakes, in-memory replacements, patching and
  monkey-patching.
- Required: real DB connections, real external calls, real filesystem, real
  network.

Use a dedicated test environment with real services. Clean up test data after
each test or session. Write down how to set up the environment.

### Parameterize for coverage

Put the cases in a table and run each one as a named subtest (`t.Run`), so a
failure names the case.

## TypeScript tests

Write new TypeScript suites with `bun:test` (`describe` / `test` / `expect`),
never a hand-rolled harness. To convert an existing hand-rolled harness, follow
docs/agents/bun-test-migration.md.

## runn scenario tests

`runn` is a scenario runner for API and CLI testing, driven by YAML.

- Files: runbooks and their `vars/` files are `*.yaml` (never `.yml`).
- Terms: a *runbook* is the YAML scenario; a *step* is one HTTP or command
  action; *vars* are values passed between steps.
- Make scenarios realistic. They do not need unit- or integration-level
  coverage.
- A2A protocol scenarios follow JSON-RPC 2.0.
- Describe each step from the **agent's point of view**:
  - good: `Agent requests task delegation`
  - bad:  `POST to /jsonrpc endpoint`
