# autoreview

Claude Code plugin that reviews and fixes code in a keep/revert loop, using the
guardrails Semgrep rules in [`.semgrep/rules/guardrails/`](../../.semgrep/rules/guardrails/),
one directory per rule category.

## Modes

- **scan-fix**: scans existing code with Semgrep, fixes one finding per
  iteration, and keeps the fix only if it lowers the findings count (or keeps
  it equal with simpler code).
- **spec-review**: reviews type definitions, interfaces, and specs before the
  code exists. An LLM judge applies the guardrails rules and scores each
  category from 1 to 10.

Languages: Go, Python, TypeScript.

## Use it

```text
/autoreview:review                  # interactive setup
/autoreview:review apr16-naming     # start or resume with a tag
```

The first run calls the `setup-review` skill. It creates the `review/<tag>`
branch, `review-config.yaml`, and `review-results.tsv`. The `reviewer` agent
runs each iteration. A PreToolUse hook asks for confirmation before an edit
outside `target_paths`.

Other skills:

- `/autoreview:analyze-results` summarizes `review-results.tsv`.
- `/autoreview:distill-rule` turns a finding or a kept fix into a new Semgrep
  rule with tests under the project's `.semgrep/`.

## Prerequisites

- `semgrep` on PATH.
- The rules at `.semgrep/rules/guardrails/` of this repository.
  `scripts/resolve-guardrails.sh` looks for them under the git root, then two
  levels above the plugin.
- `jq` on PATH (without it the scope hook does nothing).
