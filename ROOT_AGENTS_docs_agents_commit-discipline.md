# Commit Discipline

Read this before writing a commit message. Root summary is in AGENTS.md.

## Pre-commit conditions (ALL must hold)

- All tests pass.
- Zero ruff violations, zero mypy errors.
- Zero semgrep findings under `.semgrep/` (when it exists).
- The change is a single logical unit of work.
- Message follows Conventional Commits v1.0.0.

`just check` runs the whole gate; the git pre-commit hook runs it too, so a red
tree cannot be committed (see docs/agents/enforcement.md).

## Format

```
<type>(<scope>)<!>: <subject>

<body>

<footer>
```

- Subject: imperative mood, lowercase, no trailing period, ≤72 chars.
- Scope: optional but recommended in monorepos / multi-module repos
  (e.g. `feat(sightjack):`).
- Breaking change: `!` after type/scope **and** a `BREAKING CHANGE:` footer.

## Type ⇄ Tidy First mapping (fixed — mixing is forbidden)

Each type is permanently either behavioral or structural. One commit = one type.
If a change needs two types, it needs two commits — structural first.

**Behavioral** (changes what the system does):

| type   | meaning                                          |
| ------ | ------------------------------------------------ |
| `feat` | new feature (behavior added)                     |
| `fix`  | bug fix (behavior corrected)                     |
| `perf` | performance change (measurable behavior change)  |

**Structural** (no behavior change):

| type       | meaning                                            |
| ---------- | -------------------------------------------------- |
| `refactor` | restructuring without behavior change              |
| `style`    | formatting, whitespace, naming                     |
| `test`     | add/fix tests (no production behavior change)      |
| `docs`     | documentation only                                 |
| `chore`    | tooling, dependency bumps without behavior impact  |
| `build`    | build system or external dependency changes        |
| `ci`       | CI/CD configuration changes                        |

Never add `[STRUCTURAL]` / `[BEHAVIORAL]` tags — the type already encodes it.

## Examples

Good:

```
feat(auth): add refresh token rotation
refactor(paintress): extract gauge tracker into dedicated module
fix(d-mail): handle empty outbox on startup
chore(deps): bump otelcol-contrib to 0.110.0
```

Bad:

```
update stuff
feat: refactor auth and add new endpoint     # two types in one commit
[BEHAVIORAL] feat: add login                  # redundant tag
```

## Practice

- Small, frequent commits over large, infrequent ones.
- When you catch yourself wanting an "and" in the subject, split the commit.
