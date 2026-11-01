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
  is not e2e: move it to integration. The agent-baseline Semgrep rule checks Python test files whose path contains
  `e2e` (a directory such as `tests/e2e/`, or a file such as
  `test_checkout_e2e.py`), so give e2e tests such a path. The name only picks
  the files to check; the kind still depends on what the test touches. Review
  enforces the rule everywhere else (see docs/agents/semgrep.md).

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
failure names the case. Assert the status and the response body, and compare
JSON bodies as decoded values, not as strings.

### Web and mobile apps: `e2e` (tester-army/e2e)

Write new end-to-end suites for web and mobile apps with `e2e`
(https://github.com/tester-army/e2e): Playwright for browsers, agent-device for
iOS and Android simulators and emulators. These suites use the `test` of their
engine (`@e2e-dev/web`, `@e2e-dev/mobile`) and the `expect` of `e2e`, not
`bun:test`. Existing suites in another framework stay until someone migrates
them. Exploratory checks that are not a committed suite (a bug bash,
dogfooding) are not covered.

- Install a version that has passed the dependency cooldown, pinned exactly:
  `bun add -d --exact e2e@<version>` and the engine package the same way. Run
  it from a root `just` recipe with `bunx --no-install e2e run`, so it never
  fetches an unpinned copy. Never `npx`. It is pre-1.0, so read the release
  notes on every bump (docs/agents/dependency-policy.md).
- The e2e rules above still apply: real dependencies, no mocks.
- Agent steps (`agent.act`) are recorded and replayed. That cuts model calls
  but does not remove them: a step with no recording, a retry, and every
  agent judgment (`agent.assert`, `agent.waitFor`, `agent.extract`) call the
  model. Give each `agent.act` one goal, decide pass or fail with locator
  assertions (`expect(...)`), and keep agent judgments out of a required CI
  suite.
- Run the required CI job with `CI=1 bunx --no-install e2e run --strict-cache
  --retries 0`, and set no positive `retries` on a test or a `describe` in that
  suite: they override the flag, and a retry runs every goal live. A stale
  recording then fails instead of quietly running live.
- A step that was never recorded still runs live, so the required job needs a
  model credential as a CI secret. Cap the spend on the provider side (a key
  with a spend or token limit), and bound the job with `--max-duration` and
  `timeout-minutes`; `--max-failures` only stops a broken run early. If the
  provider cannot cap spend, keep agent steps out of the required job.
- Commit the replay cache (`.e2e/cache/`) and review it like test code: it
  stores typed values verbatim and replays with your permissions. Register
  every credential as a `Secret`, so the cache stores only its name.
- Turn off its telemetry: the repo's e2e recipe and CI set
  `E2E_TELEMETRY_DISABLED=1`.
- Screenshots reach the model provider. Use test accounts, never production
  secrets.

## TypeScript tests

Write new TypeScript suites with `bun:test` (`describe` / `test` / `expect`),
never a hand-rolled harness. Web and mobile end-to-end suites are the
exception: they use `e2e` (above). To convert an existing hand-rolled harness
to `bun:test`, follow docs/agents/bun-test-migration.md.

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
