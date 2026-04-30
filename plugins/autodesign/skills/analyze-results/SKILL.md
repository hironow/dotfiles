---
name: analyze-results
description: >
  Analyze results from an autodesign exploration loop. This skill should be
  used when the user asks to "analyze design results", "show design progress",
  "summarize design exploration", "what designs worked", "design statistics",
  "which exploration axis performed best", or needs to review the results
  from design-results.tsv.
version: 0.1.0
argument-hint: "[design-results.tsv path]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# Design Exploration Results Analysis

Analyze design-results.tsv from autodesign exploration loops to extract insights,
identify patterns across exploration axes, and suggest next directions.

## Analysis Process

### 1. Load Results

Read `design-results.tsv` (or path from design-config.yaml `results_file` field).
Parse tab-separated columns (6 columns):

| Index | Field | Description |
|-------|-------|-------------|
| 0 | commit | 7-char git hash |
| 1 | composite_score | Composite score (0-100) |
| 2 | status | keep/discard/constraint_fail/crash |
| 3 | constraint | Which constraint failed, or "-" |
| 4 | axis | Exploration axis used |
| 5 | description | Short description |

### 2. Summary Statistics

Calculate and report:

- **Total iterations**: Count of all rows (excluding header)
- **Outcomes**: Count of keep / discard / constraint_fail / crash
- **Keep rate**: keeps / total
- **Baseline score**: First row's composite_score
- **Current best**: Highest composite_score among "keep" rows
- **Total improvement**: Difference between baseline and current best
- **Relative improvement**: Percentage change from baseline

### 3. Axis-Level Breakdown

For each exploration axis, calculate:

| Axis       | Tried | Kept | Rate | Best Delta | Avg Delta |
|------------|-------|------|------|------------|-----------|

### 4. Constraint Violation Patterns

Identify which constraints fail with which axes.

### 5. Exploration Coverage

Report which axes from config have been explored vs. unexplored.
Flag axes with zero attempts as unexplored.

### 6. Recommendations

Based on the analysis, suggest:

- **Exploit**: Variations on successful axes (fine-tune what worked)
- **Explore**: Axes not yet tried
- **Avoid**: Axis+constraint combinations that consistently fail
- **Simplify**: Opportunities to reduce complexity while maintaining score

## Script Usage

Use the bundled analysis script for automated parsing:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/parse-results.py design-results.tsv higher
```

This outputs JSON with summary statistics and axis-level breakdown.
