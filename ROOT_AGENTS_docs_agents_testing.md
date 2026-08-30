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

## TypeScript: `bun:test` only (and converting a hand-rolled harness to it)

New TypeScript suites use `bun:test` — `describe` / `test` / `expect`, never a
hand-rolled `let pass = 0; const ok = (name, cond) => …` harness. When migrating
an existing hand-rolled leaf, the conversion is **behaviour-preserving**: same
inputs exercised, same failures caught. What follows is the rule, measured
against 7 converted leaves (2026-08-31).

### The naive transform is wrong

```ts
ok("名", 条件, 補足)  →  test("名", () => { expect(条件).toBe(true) })   // ✗
```

Bun's own docs list `expect(users.length === 3).toBe(true)` under **Avoid**: the
condition collapses to `true`/`false` before `expect` sees it, so the failure
message says `expected true, got false` and names neither side. Convert to the
matcher that carries the values:

```ts
expect(xs.length).toBe(3)            // not expect(xs.length === 3).toBe(true)
expect(() => f(bad)).toThrow("用途")  // not a try/catch + flag
expect(offenders).toEqual([])        // not expect(offenders.length === 0).toBe(true)
```

`toEqual([])` on a **collected list of offenders** is the highest-value shape:
the failure prints exactly which items broke, which the old `ok()` never did.

### Loops and shared state

- A `console.log("\n── 節 ──")` section header becomes a `describe`.
- `const` computed between `ok()` calls stays where it is — inside the
  `describe` body. Only promote to `beforeAll` if it is expensive or mutable.
- **A loop over a small fixed table becomes `test.each`** — one named case per
  row, so a failure names the row.
- **A loop over a large collection does NOT become one test per item.** A
  1346-word × 2-locale loop produced 2692 assertions; as tests that is
  unreadable and slow. Collapse it to one assertion over the collected
  offenders, and **keep a separate non-emptiness guard** so an empty collection
  can't pass silently:

```ts
test("語を歩けている", () => { expect(WORDS.length).toBeGreaterThanOrEqual(30) })
test("どの語にも両言語が在る", () => {
  const missing = WORDS.flatMap(([p, w]) =>
    LOCALES.filter((lo) => t(w, lo).trim() === "").map((lo) => `${p} の ${lo}`))
  expect(missing).toEqual([])
})
```

- Drop the trailing `console.log(\`${pass} passed\`)` and `process.exit(1)`
  entirely — the runner owns the tally and the exit code.

### `test.each` type traps

- A **`readonly` array of primitives fails to type-check**: `readonly Locale[]`
  matches none of bun's three `.each` overloads (the tuple overload takes
  `readonly` but wants tuples; the flat overload wants a mutable array), and the
  callback argument degrades to `unknown`. Pass a copy: `test.each([...LOCALES])`.
  This produced 58 type errors in one leaf and **zero** runtime failures — it is
  invisible unless the leaf is inside a type-checked program.
- `%s` interpolates a positional arg, `%j` a JSON value, `$prop` a field of an
  object row.

### Proving equivalence

Assertion count is **not** the criterion — it legitimately moves in both
directions (a mass loop collapses; a one-line `every()` over 8 bad inputs
expands into 8 named `test.each` rows). Require instead:

1. The converted leaf is **green**, and its coverage is accounted for — either
   the count matches the baseline, or every difference is explained by a
   collapse or expansion you can name.
2. **Red is preserved**: break one assertion, confirm the leaf fails, restore.
   A conversion that silently stops asserting looks exactly like a passing one.
3. The leaf is inside a **type-checked program** (see below) — `bun test` alone
   will not catch the `.each` trap above.

### Mechanical conversion doesn't work

A script that finds `ok(…)` call boundaries by counting parens **cannot parse
TypeScript**: a regex literal such as `/^(OL|FI)[\s(（]/` has an unbalanced `(`
inside a character class and throws the count off, silently producing a
malformed file. Convert by hand, or by narrow single-line edits, and run every
converted leaf.

### During a dual-runner migration

While both runners exist, **never keep a hand-written roster of which leaf runs
where.** Forget an entry and the old runner skips it ("it imports `bun:test`")
while the new one never lists it ("not on the roster") — the leaf runs *nowhere*
and the suite still goes green. Derive the set from the files themselves (grep
for the `bun:test` import) in one script that every consumer reads: the old
runner, the new runner, and the type-config guard.

### Type seat

`@types/bun` replaces the ambient `fetch` with Bun's, which carries
`preconnect`; any `typeof fetch` injection point then fails with TS2741. So bun
types usually cannot go into the shared program, and migrated leaves need a
second tsconfig. Two programs means a leaf can fall out of *both* — add a guard
test that walks the derived list and asserts each leaf is excluded from the
shared program and included in the bun one.

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
