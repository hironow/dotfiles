---
name: review-loop
description: >
  Core methodology reference for the autoreview keep/revert cycle.
  This skill provides the rules and decision logic used by the reviewer
  agent during each iteration. Not invoked directly by users — loaded
  automatically when the reviewer agent needs to make keep/revert decisions.
  For the user-facing entry point, see the review skill.
version: 0.1.0
---

# Review Loop Methodology

The autoreview loop follows a strict modify-evaluate-decide cycle inspired
by autoresearch. Each iteration targets one category of guardrails rules
applied to one file (or a small group of related files).

## Cycle Steps

### 1. Scan (Before)

**scan-fix mode:**

```bash
RULES=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/resolve-guardrails.sh")
semgrep --config "${RULES}/<category>/" --json <target_file> 2>/dev/null
```

Record `findings_before` count.

**spec-review mode:**
Read the target file and evaluate against guardrails principles for the
current category. Assign a quality score (1-10) as `findings_before`
(inverted: 10 - score, so lower = better, consistent with scan-fix).

### 2. Analyze

Parse findings and identify the root cause pattern. Group related findings
that share the same fix. Prioritize fixes by impact:

1. Fixes that resolve multiple findings at once
2. Simple renames or restructuring
3. Deeper refactoring (extract method, introduce type)

### 3. Fix

Apply the fix. Follow these constraints:

- Modify only files within `target_paths` from config
- Fix one logical concern per iteration (related findings OK)
- Preserve existing behavior — structural changes only
- Never introduce new dependencies

### 4. Commit

```bash
git add <modified_files>
git commit -m "review(<category>): <concise description>"
```

### 5. Rescan (After)

Run the same scan as step 1. Record `findings_after` count.

### 6. Decide

Keep if findings decreased; revert if unchanged or increased. For scan-fix,
also revert on cross-category regressions. For spec-review, compare LLM
quality scores. See `references/decision-logic.md` for the complete decision
matrix, special cases, and infinite loop prevention rules.

### 7. Record

Append to review-results.tsv (tab-separated):

```
<commit>\t<mode>\t<category>\t<file>\t<findings_before>\t<findings_after>\t<status>\t<description>
```

### 8. Git Action

- **keep**: Commit stays, proceed to next iteration
- **revert**: `git reset --hard HEAD~1`, try a different approach or skip

## Loop Control

### Category Progression

Process categories in order of most findings to least. Within a category,
process files with the most findings first.

### Stall Detection

Track consecutive iterations with no improvement per category.
When `max_consecutive_no_improvement` is reached, log a "skip" entry
and move to the next category.

### Iteration Limits

Each category has `max_iterations_per_category` attempts. After reaching
the limit, move to the next category regardless of remaining findings.

## Additional Resources

### Reference Files

For the detailed keep/revert decision matrix:

- **`references/decision-logic.md`** — Complete decision criteria for both modes
