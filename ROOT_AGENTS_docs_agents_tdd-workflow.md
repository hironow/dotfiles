# TDD Workflow (Red → Green → Refactor)

Read this when you are in the implementation loop. The root contract is in
AGENTS.md; this file is the full procedure.

## The cycle

1. **Red** — write the simplest *failing* test that defines one small increment
   of behavior. Use a behavior-describing name
   (`test_should_sum_two_positive_numbers`). Make the failure message clear.
2. **Green** — write the *minimum* code to pass. No more. With type annotations.
3. **Verify** — run `just check` (the full gate). When running pieces
   individually, format before linting: `just fmt` → `just lint` →
   `just semgrep` (when `.semgrep/` exists) → `just test`.
4. **Refactor** — only on green. One refactoring at a time; run tests after each.
   Prioritize removing duplication and clarifying intent.
5. **Commit** — structural and behavioral changes as *separate* commits
   (Tidy First). See docs/agents/commit-discipline.md.
6. Repeat for the next increment.

Always: one test at a time → make it run → improve structure. Run all tests
(except long-running) each time.

## Fixing a defect

1. Write a failing test at the API level that expresses the defect.
2. Write the smallest test that reproduces the root cause.
3. Make both pass.

## Tidy First — structural vs behavioral

- **Structural**: rearranging code without changing behavior (rename, extract,
  move). Validate behavior is unchanged by running tests before *and* after.
- **Behavioral**: adding or changing functionality.
- Never mix them in one commit. When a change needs both, do the structural part
  first, commit it, then the behavioral part.

## Worked example — adding a validator

**[Red]** failing test:

```python
def test_validate_email_rejects_missing_at_symbol() -> None:
    # given
    invalid_email = "userexample.com"

    # when
    result = validate_email(invalid_email)

    # then
    assert result is False
```

**[Green]** minimum implementation (typed):

```python
def validate_email(email: str) -> bool:
    return "@" in email
```

**[Verify]**:

```sh
just check    # the full gate: fmt + lint + types + semgrep + test
# or piecewise (format before linting):
just fmt      # uv run ruff format .
just lint     # uv run ruff check . && uv run mypy .
just semgrep  # when .semgrep/ exists
just test     # uv run pytest
```

**[Refactor]** (separate commit) — extract once a pattern emerges:

```
refactor(validation): extract email validator into dedicated module
```

## Test mechanics

- Structure every test as **given / when / then**.
- No try/except inside tests. Keep tests flat; avoid deep nesting.
- Prefer function-based tests over class-based.
- Only import helpers from `tests/utils/`.
- Prefer real code over mocks; parameterize when several similar scenarios exist.
- For *which* test type and the mock policy per type, see docs/agents/testing.md.
