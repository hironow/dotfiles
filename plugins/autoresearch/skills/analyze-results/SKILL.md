---
name: analyze-results
description: >
  Summarize and interpret results.tsv from an autoresearch loop: progress,
  outcomes, failure patterns and recommended next experiments. Use for any
  request to review, analyze or report on experiment progress.
argument-hint: "[results.tsv path]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# Experiment Results Analysis

Analyze results.tsv from autoresearch experiment loops to extract insights,
identify patterns, and suggest next experiment directions.

## Analysis Process

1. Run the bundled parser and take its numbers as-is:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/parse-results.py results.tsv <lower|higher>`
   (direction from `metric_direction` in experiment-config.yaml). It returns
   JSON with totals, outcome counts, keep rate, baseline, current best and
   improvement.
2. Failure analysis (judgment): from the discard/crash rows, identify which
   kinds of changes fail and any crash patterns (OOM, timeout, divergence).
3. Recommendations (judgment): exploit what worked, explore untried directions,
   look for simplifications, name failure categories to avoid.

## Output Format

Present results as a structured report:

```
## Experiment Report: <tag>

### Summary
- Total: N experiments (K kept, D discarded, C crashed)
- Keep rate: X%
- Baseline: <value> -> Current best: <value> (Y% improvement)

### Progress
[Table of kept experiments with deltas]

### Top Improvements
[Ranked list of experiments by improvement magnitude]

### Failure Patterns
[Common failure modes]

### Recommended Next Steps
1. [Specific suggestion based on data]
2. [Another suggestion]
3. [Another suggestion]
```
