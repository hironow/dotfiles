---
name: analyze-results
description: >
  This skill should be used when the user asks to "analyze review results",
  "show review progress", "summarize review", "what was fixed",
  "review-results report", "how did the review go", or wants to understand
  the outcomes of an autoreview loop. Parses review-results.tsv and presents
  a structured summary.
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# Analyze Review Results

Parse review-results.tsv and present a structured summary of the autoreview
loop outcomes.

## Analysis Steps

### 1. Compute the statistics

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/parse-results.py" review-results.tsv
```

If the file does not exist, tell the user no review has been run yet.

### 2. Read the patterns and recommend

Identify patterns in the results:

- Categories where most fixes succeeded (high keep rate)
- Categories where fixes struggled (high revert rate)
- Files that were touched most frequently
- Oscillation patterns (alternating keep/revert)

Based on the analysis, suggest:

- Categories worth re-running with a different strategy
- Files that may need manual review
- Whether another review pass would be productive
- Estimated remaining work

## Output Format

Present the analysis in a structured format:

```
## Review Summary

- Mode: scan-fix / spec-review
- Branch: review/<tag>
- Total iterations: N
- Keep rate: X%
- Net findings reduction: N → M (-K)

## Category Breakdown
[table]

## Top Fixed Files
[list]

## Recommendations
[bullets]
```
