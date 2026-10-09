# TDD Workflow (Red → Green → Refactor)

Read this when you are in the implementation loop. AGENTS.md has the root
rule; this file has the full procedure.

## The cycle

1. **Red** — Write the simplest *failing* test for one small step of behavior.
   Give it a name that describes the behavior
   (`test_should_sum_two_positive_numbers`). Make the failure message clear.
2. **Green** — Write the *minimum* code that passes. No more. Add type
   annotations.
3. **Verify** — Run `just check` (the full gate). If you run the steps one by
   one, format before you lint: `just fmt` → `just lint` → `just semgrep`
   (when `.semgrep/` exists) → `just test`.
4. **Refactor** — Only on green. Do one refactoring at a time and run the tests
   after each. Remove duplication and make the intent clear first.
5. **Commit** — Commit structural and behavioral changes *separately*
   (Tidy First). See docs/agents/commit-discipline.md.
6. Repeat for the next step.

Always: write one test at a time → make it run → improve the structure. Run
all tests (except long-running ones) each time.

## Fixing a defect

1. Write a failing test at the API level that shows the defect.
2. Write the smallest test that reproduces the root cause.
3. Make both pass.

## Tidy First — structural vs behavioral

- **Structural**: you rearrange code without changing behavior (rename,
  extract, move). Run the tests before *and* after to confirm the behavior did
  not change.
- **Behavioral**: you add or change functionality.
- Never mix the two in one commit. When a change needs both, do the structural
  part first, commit it, then do the behavioral part.

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
just lint     # uv run ruff check . && uv run ty check
just semgrep  # when .semgrep/ exists
just test     # uv run pytest
```

**[Refactor]** (separate commit) — extract the code once a pattern appears:

```
refactor(validation): extract email validator into dedicated module
```

## How to write a test

- Structure every test as **given / when / then**.
- Do not put try/except inside tests. Keep tests flat; avoid deep nesting.
- Prefer tests written as functions over classes.
- Import helpers only from `tests/utils/`.
- Prefer real code over mocks. When several scenarios are alike, parameterize.
- docs/agents/testing.md says *which* test type to write and the mock policy
  for each type.
