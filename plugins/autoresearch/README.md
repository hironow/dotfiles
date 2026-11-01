# autoresearch

Claude Code plugin that runs an experiment loop on your code. It changes the
target files, measures a fixed metric, and keeps a change only when the metric
improves. It is inspired by
[karpathy/autoresearch](https://github.com/karpathy/autoresearch).

## How it works

```text
LOOP:
  1. Form a hypothesis
  2. Change the target files
  3. git commit
  4. Run the evaluation (with a timeout)
  5. Read the metric
  6. Keep if it improved, otherwise revert
  7. Append the result to results.tsv
```

The evaluation never changes, and an equal metric with simpler code also
counts as a win. The rules and the decision tree are in
[skills/research-loop/SKILL.md](skills/research-loop/SKILL.md).

Good fits: run time or memory, hyperparameters, prompt scores, test coverage,
and bundle size.

## Use it

Claude Code installs this plugin from the `hironow-plugins` marketplace
(`just claude-plugins-install`). To load a local copy:

```bash
claude --plugin-dir plugins/autoresearch
```

| Command | What it does |
| --- | --- |
| `/autoresearch:research [tag]` | Sets up (if needed) and runs the loop |
| `/autoresearch:analyze-results` | Reports progress, keep rate, and next experiments |

The first run calls the `setup-experiment` skill. It creates the
`experiment/<tag>` branch, `experiment-config.yaml`, and `results.tsv`, then
measures the baseline. The `researcher` agent runs each iteration. A
PreToolUse hook asks for confirmation before an edit outside `target_files`.

The config fields are in
[skills/research-loop/SKILL.md](skills/research-loop/SKILL.md).

## Dependencies

Git, python3 (results parser), and jq (without jq the scope hook does
nothing).
