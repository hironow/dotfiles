# .semgrep/

Semgrep rules for this repository, one directory per category. Each rule file
sits next to its test fixture (same base name, any extension).

| Rule file | What it checks | Runs in |
| --- | --- | --- |
| [`rules/meta/compose-v1-filename-must-be-sentineled.yaml`](rules/meta/compose-v1-filename-must-be-sentineled.yaml) | In rule files (`ROOT_AGENTS.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`), every literal Compose v1 filename sits inside a `<prohibited-filename>` tag, so a rule file never breaks its own rule | `just check`, `just meta-semgrep` |
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
