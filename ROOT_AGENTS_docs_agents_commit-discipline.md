# Commit Discipline

Read this before you write a commit message. AGENTS.md has the short version.

## Before you commit, all of these must hold

- All tests pass.
- ruff reports zero violations and ty reports zero diagnostics.
- semgrep reports zero findings under `.semgrep/` (when it exists).
- The change is one logical unit of work.
- The message follows Conventional Commits v1.0.0.

`just check` runs the whole gate. The git pre-commit hook runs it too, so you
cannot commit a red tree (see docs/agents/enforcement.md).

## Format

```
<type>(<scope>)<!>: <subject>

<body>

<footer>
```

- Subject: imperative mood, lowercase, no period at the end, 72 characters at most.
- Scope: optional, but recommended in monorepos and multi-module repos
  (for example `feat(sightjack):`).
- Breaking change: put `!` after the type or scope **and** add a
  `BREAKING CHANGE:` footer.

## Each type is either behavioral or structural (fixed — never mix)

Every type is always behavioral or always structural. One commit has one type.
If a change needs two types, make two commits, structural first.

**Behavioral** — changes what the system does:

| type   | meaning                                          |
| ------ | ------------------------------------------------ |
| `feat` | new feature (behavior added)                     |
| `fix`  | bug fix (behavior corrected)                     |
| `perf` | performance change (measurable behavior change)  |

**Structural** — does not change behavior:

| type       | meaning                                            |
| ---------- | -------------------------------------------------- |
| `refactor` | restructuring without behavior change              |
| `style`    | formatting, whitespace, naming                     |
| `test`     | add/fix tests (no production behavior change)      |
| `docs`     | documentation only                                 |
| `chore`    | tooling, dependency bumps without behavior impact  |
| `build`    | build system or external dependency changes        |
| `ci`       | CI/CD configuration changes                        |

Never add `[STRUCTURAL]` or `[BEHAVIORAL]` tags. The type already says which
one it is.

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

- Make small, frequent commits, not large, rare ones.
- If you want to write "and" in the subject, split the commit.
