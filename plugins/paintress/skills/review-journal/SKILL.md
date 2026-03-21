---
name: review-journal
description: >-
  This skill should be used when the user asks to "review expedition results",
  "analyze journal", "show expedition progress", "what was fixed",
  "/review-journal", or wants to see statistics and patterns from
  completed expeditions. Also applicable when the user asks about
  "expedition success rate" or "how many issues were fixed".
version: 0.2.0
argument-hint: "[journal.tsv path] or empty for default"
allowed-tools: ["Read", "Bash", "Grep", "Glob"]
---

# Review Journal — Expedition Results Analysis

Analyze `journal.tsv` to report on expedition progress, success rates, failure patterns, and recommended next actions.

## Analysis Process

### 1. Load Data

Read `journal.tsv` (from argument or from `continent-config.yaml`'s `journal_file` field).
Parse as TSV with columns: `issue`, `commit`, `status`, `pr_url`, `description`.

### 2. Compute Statistics

Calculate and present:

```
## Expedition Report

### Summary
- Total expeditions: N
- Success: K (X%)
- Failed: F (Y%)
  - Compile errors: C1
  - Test failures: C2
  - Timeouts: C3
- Skipped: S
  - No DoD: S1
  - Conflicts: S2
  - Duplicates: S3
```

### 3. Progress Timeline

List all successful expeditions in order:

```
### Completed Fixes
| # | Issue | Description | PR |
|---|-------|-------------|----|
| 1 | MY-473 | #123 partial axes handling | PR #58 |
| 2 | MY-520 | #169 empty body guard | PR #58 |
```

### 4. Failure Analysis

Group failures by category and identify patterns:

```
### Failure Patterns
- fail:compile (3 occurrences): MY-529, MY-530, MY-531
  → All in internal/session/ — may indicate shared dependency issue
- fail:test (2 occurrences): MY-540, MY-541
  → Both involve concurrency — consider race condition
```

### 5. Recommendations

Based on patterns, suggest:
- Which failure categories to investigate manually
- Whether to retry failed issues with different approach
- If success rate is below 50%, suggest config or scope adjustments
- Next batch of issues to target

## Output Format

Present the report directly in conversation. Use markdown tables for structured data. Keep it concise — focus on actionable insights.

## Script Utility

For JSON output, run:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/parse-journal.py <journal_file>
```
