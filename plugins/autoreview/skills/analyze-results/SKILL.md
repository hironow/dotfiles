---
name: analyze-results
description: >
  This skill should be used when the user asks to "analyze review results",
  "show review progress", "summarize review", "what was fixed",
  "review-results report", "how did the review go", or wants to understand
  the outcomes of an autoreview loop. Parses review-results.tsv and presents
  a structured summary.
version: 0.1.0
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

### 1. Read Results

```bash
cat review-results.tsv
```

If the file does not exist, inform the user that no review has been run yet.

### 2. Compute Summary Statistics

Calculate from the TSV data:

- **Total iterations**: Count of all rows (excluding header)
- **Kept**: Count where status = "keep"
- **Reverted**: Count where status = "revert"
- **Skipped**: Count where status = "skip"
- **Keep rate**: kept / total iterations
- **Net findings reduction**: First findings_before minus last findings_after

### 3. Per-Category Breakdown

For each category that appears in the results:

| Category | Iterations | Kept | Reverted | Findings Start | Findings End | Reduction |
|----------|-----------|------|----------|---------------|-------------|-----------|

### 4. Per-File Breakdown

For each file that appears in the results:

- Files with most fixes applied
- Files with most reverts (indicating difficulty)
- Files with remaining findings

### 5. Pattern Analysis

Identify patterns in the results:

- Categories where most fixes succeeded (high keep rate)
- Categories where fixes struggled (high revert rate)
- Files that were touched most frequently
- Oscillation patterns (alternating keep/revert)

### 6. Recommendations

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
