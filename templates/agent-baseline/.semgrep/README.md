# Semgrep ruleset

Project-specific static analysis. These rules mechanically enforce decisions that
are otherwise only advisory in `AGENTS.md` / `docs/agents/`. Full philosophy and
conventions: `docs/agents/semgrep.md`.

## Layout

```
.semgrep/rules/{category}/{rule-id}.yaml    # one rule per file, id == filename
.semgrep/tests/{category}/{rule-id}.{py,…}  # >=1 positive (# ruleid:) + 1 negative (# ok:)
```

## Run

```sh
just semgrep                              # = semgrep --config .semgrep/rules/ --error
semgrep --test --config .semgrep/rules/ .semgrep/tests/   # validate the rules themselves
```

CI runs `just semgrep` as part of the required quality gate; the pre-commit hook
runs it too. `.semgrepignore` at the repo root keeps `tests/` in scope (Semgrep
skips it by default when that file is missing) and leaves out the rule fixtures
in `.semgrep/tests/`.

## Current rules

| id                                    | enforces                                  |
| ------------------------------------- | ----------------------------------------- |
| `agentcore-testing-no-mock-in-e2e`    | no mocks or patching in Python test files whose path contains `e2e` |
| `agentcore-python-no-os-path`         | `pathlib.Path` instead of `os.path`       |

## Adding a rule

Add the rule the **second** time the same issue shows up in review. Use the id
format `{project-prefix}-{category}-{short-name}`, `.yaml` extension, and include
a test file with at least one match and one non-match. Link the backing ADR in
`metadata.adr` when the rule enforces an ADR decision.
