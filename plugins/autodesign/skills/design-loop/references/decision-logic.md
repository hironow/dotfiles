# Decision Logic Reference

## Complete Decision Tree

```
Experiment completed
|
+-- Evaluation successful?
|   |
|   +-- YES: Check constraints
|   |   |
|   |   +-- ANY constraint violated?
|   |   |   |
|   |   |   +-- YES: Log "constraint_fail", record which constraint
|   |   |   |   +-- git reset --hard HEAD~1
|   |   |   |   +-- Record axis+constraint pair for future avoidance
|   |   |   |
|   |   |   +-- NO: Compare composite_score with current best
|   |   |       |
|   |   |       +-- Score improved?
|   |   |       |   |
|   |   |       |   +-- YES: Apply simplicity criterion
|   |   |       |   |   |
|   |   |       |   |   +-- Code deleted (net negative LOC)?
|   |   |       |   |   |   +-- ALWAYS KEEP (simplification win)
|   |   |       |   |   |
|   |   |       |   |   +-- Improvement > 1% relative?
|   |   |       |   |   |   +-- KEEP (significant gain)
|   |   |       |   |   |
|   |   |       |   |   +-- Improvement 0.1%-1% relative?
|   |   |       |   |   |   +-- KEEP if complexity increase is small
|   |   |       |   |   |   +-- REVERT if complexity increase is large
|   |   |       |   |   |
|   |   |       |   |   +-- Improvement < 0.1% relative?
|   |   |       |   |       +-- KEEP only if code is simpler or equal
|   |   |       |   |       +-- REVERT if any complexity added
|   |   |       |   |
|   |   |       |   +-- NO: Score same or worse
|   |   |       |       +-- REVERT (git reset --hard HEAD~1)
|   |   |       |
|   |   |       +-- (Log result to design-results.tsv regardless)
|   |   |
|   |   +-- Constraint mapping:
|   |       structure_errors_max -> structure_errors from structure.sh
|   |       aeo_score_min -> aeo_score from readability.sh
|   |       lighthouse_avg_min -> lighthouse_avg from lighthouse.sh
|   |       completeness_score_min -> completeness_score from completeness.sh
|   |
|   +-- NO: Extraction failed (empty grep)
|       |
|       +-- Run crashed
|           |
|           +-- Trivial fix possible (typo, syntax error)?
|           |   +-- Fix, re-commit, re-run (max 1 retry)
|           |
|           +-- Fundamental issue?
|               +-- Log "crash" to design-results.tsv
|               +-- git reset --hard HEAD~1
|               +-- Move on to next hypothesis
```

## Constraint Check Examples

### Constraint Pass

```
structure_errors: 1 (max: 3) -> PASS
aeo_score: 65 (min: 50) -> PASS
lighthouse_avg: 82 (min: 70) -> PASS
completeness_score: 75 (min: 60) -> PASS
constraint_violated: none
```

### Constraint Fail

```
structure_errors: 5 (max: 3) -> FAIL
constraint_violated: structure_errors_max
Decision: REVERT regardless of composite_score
```

## Simplicity Criterion Examples

### Keep: Significant improvement

```
Before: composite_score = 78.5
After:  composite_score = 82.1 (4.6% improvement)
Change: Restructured hero section layout (+12 LOC)
Decision: KEEP - significant improvement justifies moderate complexity
```

### Keep: Simplification win

```
Before: composite_score = 82.1, 180 LOC
After:  composite_score = 81.8, 145 LOC (deleted 35 lines)
Decision: KEEP - minor score decrease but major simplification
```

### Revert: Marginal gain with high complexity

```
Before: composite_score = 82.1
After:  composite_score = 82.2 (0.1% improvement)
Change: Added 40 lines of animation CSS
Decision: REVERT - marginal gain does not justify complexity
```

### Revert: Constraint violation

```
Before: composite_score = 82.1
After:  composite_score = 88.5 (7.7% improvement!)
But:    structure_errors = 8 (max: 3) -> CONSTRAINT FAIL
Decision: REVERT - constraint violation overrides score improvement
```

## Git Operations

### Advance branch (keep)

The commit from step 4 stays. Branch pointer advances.
No additional git operation needed.

### Revert (discard or constraint_fail)

```bash
git reset --hard HEAD~1
```

### Crash recovery

```bash
# Check what went wrong
tail -n 50 run.log

# If fixable
git commit --amend -m "design(<axis>): <description> (fix)"
# Re-run evaluation

# If not fixable
git reset --hard HEAD~1
```
