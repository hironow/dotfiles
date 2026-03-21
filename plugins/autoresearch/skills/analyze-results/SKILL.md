---
name: analyze-results
description: >
  Analyze results from an autoresearch experiment loop. This skill should be
  used when the user asks to "analyze experiment results", "show research progress",
  "summarize experiments", "what improved", "experiment statistics", or needs to
  review and visualize the results from results.tsv.
version: 0.1.0
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

### 1. Load Results

Read `results.tsv` (or path from experiment-config.yaml `results_file` field).
Parse tab-separated columns: commit, metric, status, description.

### 2. Summary Statistics

Calculate and report:
- **Total experiments**: Count of all rows (excluding header)
- **Outcomes**: Count of keep / discard / crash
- **Keep rate**: keeps / total (higher suggests good hypothesis generation)
- **Baseline metric**: First row's metric value
- **Current best**: Lowest (or highest, per metric_direction) metric among "keep" rows
- **Total improvement**: Difference between baseline and current best
- **Relative improvement**: Percentage change from baseline

### 3. Progress Trajectory

List all "keep" experiments in order, showing cumulative improvement:

```
# | commit  | metric   | delta    | description
1 | a1b2c3d | 0.9500   | baseline | initial baseline
2 | b2c3d4e | 0.9320   | -0.0180  | increase learning rate
3 | e5f6g7h | 0.9210   | -0.0110  | reduce model depth
```

### 4. Failure Analysis

Identify patterns in discarded and crashed experiments:
- What types of changes consistently fail?
- Are there crash patterns (OOM, timeout, convergence)?
- What experiment categories have the best keep rate?

### 5. Recommendations

Based on the analysis, suggest:
- **Exploit**: Variations on successful experiments (fine-tune what worked)
- **Explore**: Novel directions not yet tried
- **Simplify**: Opportunities to reduce code while maintaining metrics
- **Avoid**: Categories of changes that consistently fail

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

## Script Usage

Use the bundled analysis script for automated parsing:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/parse-results.py results.tsv
```

This outputs JSON with summary statistics for programmatic use.
