---
name: analyze-results
description: >
  Summarize and interpret design-results.tsv from an autodesign loop: progress,
  per-axis keep rates, constraint-violation patterns, coverage and recommended
  next axes. Use for any request to review, analyze or report on design
  exploration progress.
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

1. Run the bundled parser and take its numbers as-is:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/parse-results.py design-results.tsv higher`.
   It returns JSON with totals, outcome counts, keep rate, baseline, current
   best, improvement and the per-axis breakdown (tried/kept/rate/deltas).
2. Constraint and coverage analysis (judgment): from the constraint_fail rows,
   identify which constraints fail with which axes, and compare the axes listed
   in design-config.yaml against those tried to flag unexplored ones.
3. Recommendations (judgment): exploit axes with high keep rates, explore
   untried axes, avoid axis+constraint combinations that consistently fail.
