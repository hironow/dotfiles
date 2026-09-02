---
name: design-loop
description: >
  Methodology reference for the autodesign keep/revert cycle: two-stage decision
  (constraints, then composite score), axis selection and error recovery. Use
  when the user asks how the loop decides, wants to tune the criteria, or asks
  about the autodesign pattern. Not the entry point — use /design to run a loop.
---

# Autonomous Design Exploration Loop

Core knowledge for driving iterative design exploration cycles that modify target
web artifacts, evaluate against quality constraints, and use git-based keep/revert decisions.

## Pattern Overview

The autodesign pattern applies the scientific method to web design:
hypothesize a design change, implement it, measure quality, decide keep/revert, repeat.

```
LOOP:
  1. Check git state (current branch/commit)
  2. Form design hypothesis (select exploration axis, propose change)
  3. Modify target file(s) — one axis per iteration
  4. git commit the change
  5. Run evaluation command (with timeout)
  6. Extract composite_score and constraint_violated
  7. IF constraints met AND score improved -> keep commit
     ELSE -> git reset --hard "$base" (revert to the iteration baseline
             recorded by the designer agent's Step 0 preflight; never HEAD~1)
  8. Log result to design-results.tsv
  9. GOTO 1
```

## Three Immutable Rules

1. **Immutable evaluation**: The evaluation harness (scripts, config, constraints)
   is NEVER modified during exploration. It is the ground truth.
2. **Single target**: Only designated target file(s) are modified per iteration.
   All other files remain untouched.
3. **Fixed budget**: Each iteration runs within a fixed time budget
   to ensure fair comparison across iterations.

## Two-Stage Decision

Constraints are a pass/fail gate — any violation reverts regardless of score —
and only a passing run has its composite_score compared with the current best.
Apply the full decision tree in `references/decision-logic.md`.

## Exploration Strategy

### Axis Selection

Select one exploration axis per iteration. Strategy:

1. **Unexplored axes first**: Try axes that have zero entries in results
2. **Exploit successful axes**: Deep-dive axes with high keep rates
3. **Avoid failure patterns**: Skip axis+constraint combinations that repeatedly fail
4. **One axis per change**: Never mix multiple axes in one iteration

### Hypothesis Quality

A good design hypothesis is:

- **Specific**: "Change hero section to asymmetric 60/40 grid" not "improve layout"
- **Minimal**: One focused change, not a full redesign
- **Informed**: Based on results history (what worked, what failed)
- **Constrained**: Aware of which constraints are tight

## Configuration

Define in `design-config.yaml` at project root:

```yaml
tag: "experiment-name"
target_files:
  - "src/app/page.tsx"
eval_target: "http://localhost:3000"
eval_command: "bash ${CLAUDE_PLUGIN_ROOT}/scripts/eval-composite.sh"
metric_name: "composite_score"
metric_direction: "higher"
timeout_seconds: 90
results_file: "design-results.tsv"
evaluators:
  structure: { enabled: true, weight: 0.30 }
  readability: { enabled: true, weight: 0.20 }
  lighthouse: { enabled: true, weight: 0.30 }
  completeness: { enabled: true, weight: 0.20 }
constraints:
  structure_errors_max: 3
  aeo_score_min: 50
  lighthouse_avg_min: 70
  completeness_score_min: 60
exploration_axes:
  - layout
  - color
  - typography
  - animation
  - spacing
  - imagery
```

## Results Logging

Log every iteration to design-results.tsv (tab-separated, 6 columns):

```
commit composite_score status constraint axis description
a1b2c3d 78.500000 keep - baseline initial design
b2c3d4e 82.100000 keep - layout asymmetric hero section
c3d4e5f 0.000000 constraint_fail structure animation parallax broke a11y
d4e5f6g 80.300000 discard - color dark palette attempt
```

Status values: `keep`, `discard`, `constraint_fail`, `crash`

## Error Recovery

- **Timeout**: Kill the process after timeout_seconds. Status = "crash", revert.
- **Crash**: Check run.log. If trivial fix (typo, syntax) -> fix and retry once.
  If fundamental -> log "crash", revert, move on.
- **Constraint violation**: Log which constraint failed. Use this data to avoid
  repeating the same axis+constraint failure pattern.

## Context Window Management

Each iteration runs as an independent subagent via the Agent tool to avoid
context window exhaustion. The designer agent handles one iteration per invocation.
State persists externally in git history + design-results.tsv.

## Additional Resources

### Reference Files

For detailed decision logic and criteria:

- **`references/decision-logic.md`** - Complete keep/revert decision tree with examples
