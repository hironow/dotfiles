# TDD workflow (Red → Green → Refactor)

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

## Which test to write

docs/agents/testing.md says which kind of test to write, how to write it, and
the mock policy for each kind.
