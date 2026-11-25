# .semgrep/

Semgrep rules for this repository, one directory per category. Each rule file
sits next to its test fixture (same base name, any extension).

| Rule file | What it checks | Runs in |
| --- | --- | --- |
| [`rules/meta/compose-v1-filename-must-be-sentineled.yaml`](rules/meta/compose-v1-filename-must-be-sentineled.yaml) | In rule files (`ROOT_AGENTS.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`), every literal Compose v1 filename sits inside a `<prohibited-filename>` tag, so a rule file never breaks its own rule | `just check`, `just meta-semgrep` |
| [`rules/workflow/`](rules/workflow/) | The policies the GitHub Actions workflows keep: actions pinned to a full SHA, draft pull requests skipped and woken on `ready_for_review`, caches saved only on push, gates that run `always()`, required checks without path filters, no cached Go test results, pwsh steps that stop on a failed command, pinned just, no `continue-on-error`, verified downloads, and the retired tools kept out (ADR-0093) | `just check` (over `.github/workflows/` and the `justfile`) |
| [`rules/guardrails/`](rules/guardrails/) | Architecture rules for Go, Python and TypeScript, one directory per category (naming, type safety, immutability, encapsulation, structure, complexity, layer dependency, repository, error handling, security, backward compatibility); they implement the architecture rules of [j5ik2o/ai-tools](https://github.com/j5ik2o/ai-tools) (Apache-2.0) and came from hironow/semgrep-guardrails at `3754cfe` (ADR-0094). Their fixtures are in `rules/guardrails/tests/`, not beside each rule | `just semgrep-test` (validate, and the fixtures must give findings); the autoreview plugin scans code with them |
| [`rules/mise/`](rules/mise/) | The text policies of `config/mise/config.toml`: `auto_prune = false` keeps the comment that names `just disk-gc`. Its structured policies are rules of `tools/repo-lint` (ADR-0093) | `just check` (over `config/mise/config.toml`) |
| [`rules/python/python-custom.yaml`](rules/python/python-custom.yaml) | Python style rules (specific class names, no `os.path`, no `print`, and more) | `just emu-lint`, on `emulator/` only |

`just semgrep-test` (part of `just ci`) runs every rule against its fixture.

This repository has no e2e suite, so there is no e2e rule here. The
no-mocks-in-e2e rule for repositories that have one ships with the scaffold in
[`templates/agent-baseline/.semgrep/`](../templates/agent-baseline/.semgrep/README.md).

## Adding a rule

1. Write the rule in `rules/{category}/{name}.yaml`.
2. Write the fixture next to it, `rules/{category}/{name}.{ext}`, with an
   extension the rule's `languages:` covers. Mark each line that should match
   with a `ruleid:` comment above it, and each line that should not with an
   `ok:` comment.
3. Run `just semgrep-test`.
4. Make sure a recipe scans with it (see "Runs in" above). `just semgrep-test`
   only tests the rule; it does not scan the repository.

When to write a rule, and the id format, are in the
[Semgrep spoke](../ROOT_AGENTS_docs_agents_semgrep.md).
