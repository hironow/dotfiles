---
name: research-loop
description: >
  Methodology reference for the autoresearch keep/revert cycle: rules, decision
  logic and error recovery for the modify-evaluate-decide loop. Use when the
  user asks how the loop decides, wants to tune keep/revert criteria, or asks
  about the autoresearch pattern. Not the entry point — use /research to run a
  loop.
---

# Autonomous Research Loop

Core knowledge for driving iterative experiment cycles that modify target code,
evaluate against immutable metrics, and use git-based keep/revert decisions.

## Pattern Overview

The autoresearch pattern automates the scientific method:
hypothesize, experiment, measure, decide, repeat.

```
LOOP:
  1. Check git state (current branch/commit)
  2. Form hypothesis and modify target file(s)
  3. git commit the change
  4. Run evaluation command (with timeout)
  5. Extract metrics from output
  6. Log result to results.tsv (append-only, git-untracked)
  7. IF metric improved -> keep commit (advance branch)
     ELSE -> git reset --hard "$base" (revert to the iteration baseline
             recorded by the researcher agent's Step 0 preflight; never HEAD~1)
  8. GOTO 1
```

## Three Immutable Rules

1. **Immutable evaluation**: The evaluation harness (tests, benchmarks, metrics)
   is NEVER modified during experiments. It is the ground truth.
2. **Single target**: Only designated target file(s) are modified per experiment.
   All other files remain untouched.
3. **Fixed budget**: Each experiment runs within a fixed time or resource budget
   to ensure fair comparison across iterations.

## Experiment Configuration

Before starting, define these in an `experiment-config.yaml` at project root:

```yaml
tag: "experiment-name"           # Branch name: experiment/<tag>
target_files:                    # Files the agent may modify
  - "src/algorithm.py"
eval_command: "just test"        # Command to run evaluation
metric_name: "score"             # Name of the metric to optimize
metric_direction: "lower"        # "lower" or "higher" is better
timeout_seconds: 120             # Max time per experiment run
results_file: "results.tsv"     # Append-only log (git-untracked)
```

## Decision Logic

Keep when the metric improves (or stays equal with simpler code), revert
otherwise, and log a failed run as "crash" before reverting. Apply the full
decision tree in `references/decision-logic.md`.

## Results Logging

Log every experiment to `results.tsv` (tab-separated, git-untracked):

```
commit metric status description
a1b2c3d 0.9500 keep baseline
b2c3d4e 0.9320 keep increase learning rate
c3d4e5f 0.9600 discard switch activation function
d4e5f6g 0.0000 crash double model width (OOM)
```

Columns: commit hash (7 chars), metric value (6 decimals), status (keep/discard/crash),
short description of what was tried.

## Error Recovery

- **Timeout**: Kill the process after `timeout_seconds`. Status = "crash", revert.
- **Crash (OOM, error)**: Check output logs. If trivial fix (typo, import) -> fix and retry.
  If fundamental issue -> log "crash", revert, move on.
- **Metric extraction failure**: If grep returns empty, the run crashed. Inspect logs.
- **Fast fail**: If output indicates NaN or exploding values, abort early.

## Context Window Management

Each experiment should run as an independent subagent via the Agent tool to avoid
context window exhaustion. The researcher agent handles one experiment per invocation.
State persists externally in git history + results.tsv.

## Additional Resources

### Reference Files

For detailed decision logic and criteria:

- **`references/decision-logic.md`** - Complete keep/revert decision tree with examples
