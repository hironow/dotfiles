---
name: gradient-gauge
description: >-
  Core game mechanic reference for the expedition momentum system.
  The Gradient Gauge tracks consecutive success/failure and scales
  issue difficulty accordingly. Applicable when the user asks about
  "gradient gauge", "expedition difficulty", "momentum system",
  "gradient level", or needs to understand how issue priority
  selection adapts based on past performance.
version: 0.2.0
---

# Gradient Gauge — Momentum & Difficulty Scaling

The Gradient Gauge is a momentum-based mechanic that adapts expedition difficulty
based on recent performance. Inspired by the combat system of Clair Obscur: Expedition 33.

## State

Stored in `gradient.json` (git-untracked, same directory as journal.tsv):

```json
{
  "level": 0,
  "consecutive_failures": 0,
  "consecutive_skips": 0,
  "last_status": "",
  "last_updated": ""
}
```

## Level Range: 0–5

| Level | Name | Issue Priority Hint |
|-------|------|---------------------|
| 0 | Depleted | Only pick low-priority, small-scope issues |
| 1 | Warming | Low to normal priority |
| 2 | Steady | Normal priority |
| 3 | Rising | Normal to high priority |
| 4 | Surging | High priority OK |
| 5 | Gradient Attack | Attempt the most complex/highest-priority issue available |

## State Transitions

### On Success (status = "success")

- **Charge**: `level = min(level + 1, 5)`
- Reset `consecutive_failures = 0`
- Reset `consecutive_skips = 0`

### On Skip (status starts with "skip:")

- **Decay**: `level = max(level - 1, 0)`
- Reset `consecutive_failures = 0`
- Increment `consecutive_skips += 1`

### On Failure (status starts with "fail:" or "partial:")

- **Discharge**: `level = 0`
- Increment `consecutive_failures += 1`
- Reset `consecutive_skips = 0`

## Gommage (Failure Escalation)

When `consecutive_failures >= 3` OR `consecutive_skips >= 3`:

1. **HALT** the expedition loop immediately
2. Write `gommage.md` insight file with:
   - Recent failure reasons from journal.tsv (last 3 entries)
   - Common failure patterns
   - Suggested corrective actions
3. Report gommage to the user and stop

## Priority Filtering by Gradient Level

When querying Linear issues, filter by priority based on current gradient level:

- **Level 0–1**: Filter to priority >= 3 (low priority, "No priority" or "Low")
- **Level 2–3**: No filter (all priorities)
- **Level 4–5**: Sort by priority ascending (pick highest priority first)

Linear priority values: 0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low

## Prompt Injection

Include the current gradient state in the expedition agent prompt:

```
Gradient Gauge: Level <N>/5 (<name>)
Priority hint: <hint text from table above>
Consecutive failures: <N> | Consecutive skips: <N>
```

## Script Usage

Read and update gradient state:

```bash
# Read current state
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gradient.py read gradient.json

# Update after expedition result
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gradient.py update gradient.json <status>
```

Output is JSON for programmatic use.
