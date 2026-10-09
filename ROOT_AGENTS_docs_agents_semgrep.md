# Semgrep Rules (`.semgrep/`)

Read this when you add or maintain a static-analysis rule for one project.
Start with few rules when the project starts; add rules as patterns settle.

## Why rules exist

- Rules turn the team's *unwritten* rules into checks: the things reviewers
  catch again and again.
- Write a rule the **second** time you catch the same issue in review. Once is
  a coincidence; twice is a pattern.
- The number of rules grows toward the middle of the project's life, once the
  architecture settles.

## Directory structure

```
.semgrep/rules/{category}/{rule-id}.yaml
.semgrep/tests/{category}/{rule-id}.{py|go|ts|…}
.semgrep/README.md          # ruleset overview + how to add a rule
```

## Rule file convention

- One rule per file; the filename matches the rule id.
- Use the `.yaml` extension (never `.yml`).
- Rule id: `{project-prefix}-{category}-{short-name}`
  (e.g. `paintress-concurrency-unguarded-goroutine`).
- Every rule has a test file with at least one example that matches and one
  that does not.

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

## Running the rules

- `just semgrep` runs `semgrep --config .semgrep/rules/ --error`.
- Make semgrep a required CI check before merge (see the quality-gate
  workflow).
- Pre-commit runs semgrep together with ruff and ty.

## When to add a rule

- Reviewers made the same comment twice or more.
- An ADR decision needs a mechanical check (e.g. "always Cloud SQL
  PostgreSQL, never Spanner").
- You can express the root cause of a production incident as a code pattern.

## When *not* to add a rule

- A type checker would catch it: let ty do its job.
- ruff already has a built-in rule for it.
- It would often fire false positives: tune it or drop it.
