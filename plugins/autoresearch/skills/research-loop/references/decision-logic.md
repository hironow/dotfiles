# Decision Logic Reference

## Complete Decision Tree

```
Experiment completed
|
+-- Metric extraction successful?
|   |
|   +-- YES: Compare with previous best
|   |   |
|   |   +-- Metric improved?
|   |   |   |
|   |   |   +-- YES: Apply simplicity criterion
|   |   |   |   |
|   |   |   |   +-- Code deleted (net negative LOC)?
|   |   |   |   |   +-- ALWAYS KEEP (simplification win)
|   |   |   |   |
|   |   |   |   +-- Improvement > 1% relative?
|   |   |   |   |   +-- KEEP (significant gain justifies complexity)
|   |   |   |   |
|   |   |   |   +-- Improvement 0.1%-1% relative?
|   |   |   |   |   +-- KEEP if complexity increase is small (<10 LOC)
|   |   |   |   |   +-- REVERT if complexity increase is large (>20 LOC)
|   |   |   |   |
|   |   |   |   +-- Improvement < 0.1% relative?
|   |   |   |       +-- KEEP only if code is simpler or equal
|   |   |   |       +-- REVERT if any complexity added
|   |   |   |
|   |   |   +-- NO: Metric same or worse
|   |   |       +-- REVERT (git reset --hard HEAD~1)
|   |   |
|   |   +-- (Log result to results.tsv regardless of decision)
|   |
|   +-- NO: Extraction failed (empty grep)
|       |
|       +-- Run crashed
|           |
|           +-- Trivial fix possible (typo, import)?
|           |   +-- Fix, re-commit, re-run (max 2 retries)
|           |
|           +-- Fundamental issue?
|               +-- Log "crash" to results.tsv
|               +-- git reset --hard HEAD~1
|               +-- Move on to next hypothesis
```

## Simplicity Criterion Examples

### Keep: Significant improvement

```
Before: val_bpb = 0.9979
After:  val_bpb = 0.9800 (1.8% improvement)
Change: Added 15 lines for new attention pattern
Decision: KEEP - significant improvement justifies moderate complexity
```

### Keep: Simplification win

```
Before: val_bpb = 0.9800, 45 LOC in optimizer
After:  val_bpb = 0.9805, 30 LOC in optimizer (deleted 15 lines)
Decision: KEEP - minor regression but major simplification
         (0.05% worse but 33% less code)
```

### Revert: Marginal gain with high complexity

```
Before: val_bpb = 0.9800
After:  val_bpb = 0.9795 (0.05% improvement)
Change: Added 25 lines of hacky scheduling logic
Decision: REVERT - marginal gain does not justify complexity
```

### Revert: No improvement

```
Before: execution_time = 1.23s
After:  execution_time = 1.25s (worse)
Decision: REVERT - metric did not improve
```

## Git Operations

### Advance branch (keep)

The commit from step 3 stays. Branch pointer advances.
No additional git operation needed.

### Revert (discard)

```bash
git reset --hard HEAD~1
```

This removes the last commit and restores the working tree.
The results.tsv entry preserves the record of what was tried.

### Crash recovery

```bash
# Check what went wrong
tail -n 50 run.log

# If fixable
git commit --amend -m "experiment: <description> (fix)"
# Re-run evaluation

# If not fixable
git reset --hard HEAD~1
```

## Metric Extraction Patterns

### From stdout (grep)

```bash
grep "^metric_name:" run.log | awk '{print $2}'
```

### From JSON output

```bash
python3 -c "import json; print(json.load(open('run.log'))['metric'])"
```

### From test output

```bash
# pytest with coverage
pytest --cov=src --cov-report=term | grep "TOTAL" | awk '{print $NF}'

# execution time
/usr/bin/time -f "%e" command 2>&1 | tail -1
```
