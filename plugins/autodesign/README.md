# autodesign

Claude Code plugin that explores web design variations in a loop. It keeps a
change only when it passes quality constraints and raises the composite score.
It follows the keep/revert pattern of [autoresearch](../autoresearch/).

## How it works

```text
LOOP:
  1. Pick an exploration axis and form a hypothesis
  2. Change the target files
  3. git commit
  4. Run the evaluators (with a timeout)
  5. Revert at once if a quality constraint fails
  6. Keep if composite_score improved, otherwise revert
  7. Append the result to design-results.tsv
```

Quality metrics are floors, not targets: the goal is to explore new designs,
not only to fix issues. The rules and the decision tree are in
[skills/design-loop/SKILL.md](skills/design-loop/SKILL.md).

## Use it

Claude Code installs this plugin from the `hironow-plugins` marketplace
(`just claude-plugins-install`). To load a local copy:

```bash
claude --plugin-dir plugins/autodesign
```

| Command | What it does |
| --- | --- |
| `/autodesign:design [tag]` | Sets up (if needed) and runs the loop |
| `/autodesign:analyze-results` | Reports progress, keep rate per axis, and next steps |

The first run calls the `setup-design` skill. It creates the `design/<tag>`
branch, `design-config.yaml`, and `design-results.tsv`, then measures the
baseline. The `designer` agent runs each iteration. A PreToolUse hook asks
for confirmation before an edit outside `target_files`.

The config fields, default weights, and constraints are in
[skills/setup-design/SKILL.md](skills/setup-design/SKILL.md).

## Evaluators

`scripts/eval-composite.sh` runs the enabled evaluators and prints
`composite_score`.

| Evaluator | Metric | Needs Chrome |
| --- | --- | --- |
| `structure.sh` | Pa11y a11y errors | Yes |
| `readability.sh` | AEO score (0-100) | No |
| `lighthouse.sh` | Lighthouse average (0-100) | Yes |
| `completeness.sh` | Placeholder detection (0-100) | No |
| `html-validate.sh` | HTML validation errors | No |

## Dependencies

- Required: Git, bun, bc, python3, and jq (without jq the scope hook does
  nothing).
- Optional: Chrome or Chromium (for `structure.sh` and `lighthouse.sh`), and
  yq (the config reader falls back to grep and sed without it).
