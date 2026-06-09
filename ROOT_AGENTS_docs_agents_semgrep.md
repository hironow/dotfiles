# Semgrep Rules (`.semgrep/`)

Read this when adding or maintaining a project-specific static-analysis rule.
Start light at project inception; grow rules as patterns stabilize.

## Philosophy

- Rules codify the team's *unwritten* rules — what reviewers catch repeatedly.
- Write a rule the **second** time you catch the same issue in review (once is a
  coincidence, twice is a pattern).
- Density grows toward mid-lifecycle, once architectural patterns settle.

## Directory structure

```
.semgrep/rules/{category}/{rule-id}.yaml
.semgrep/tests/{category}/{rule-id}.{py|go|ts|…}
.semgrep/README.md          # ruleset overview + how to add a rule
```

## Rule file convention

- One rule per file; filename matches the rule id.
- `.yaml` extension (never `.yml`).
- Rule id: `{project-prefix}-{category}-{short-name}`
  (e.g. `paintress-concurrency-unguarded-goroutine`).
- Every rule has a test file with at least one positive (matching) and one
  negative (non-matching) example.

## Rule template

```yaml
rules:
  - id: paintress-concurrency-unguarded-goroutine
    message: |
      Launching a goroutine without passing a context.Context is forbidden.
      Pass ctx explicitly so the caller can cancel.
    severity: ERROR
    languages: [go]
    pattern: |
      go func() {
        ...
      }()
    metadata:
      category: concurrency
      added: "2026-04-18"
      adr: docs/adr/NNNN-goroutine-context.md
```

## Execution

- `just semgrep` runs `semgrep --config .semgrep/rules/ --error`.
- Wire semgrep into CI as a required check before merge (see the quality-gate
  workflow).
- Pre-commit runs semgrep alongside ruff + mypy.

## When to add a rule

- The same review comment has been made twice or more.
- An ADR decision needs mechanical enforcement (e.g. "always Cloud SQL
  PostgreSQL, never Spanner").
- A production incident's root cause is expressible as a code pattern.

## When *not* to add a rule

- A type checker would catch it — let mypy do its job.
- ruff already has a built-in rule for it.
- It would fire false positives frequently — tune or drop it.
