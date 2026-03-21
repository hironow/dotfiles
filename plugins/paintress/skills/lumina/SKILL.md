---
name: lumina
description: >-
  Learning system that extracts success/failure patterns from past
  expedition journals and injects them into the agent prompt. Applicable
  when the user asks about "lumina", "expedition patterns", "learn from
  past expeditions", "failure patterns", "success patterns", or needs to
  understand how the expedition agent adapts based on historical data.
version: 0.2.0
---

# Lumina — Learned Passive Skills

Lumina is the expedition learning system. It scans past journal entries to
extract success and failure patterns, then injects them into the expedition
agent prompt as tactical guidance.

## Pattern Types

### Offensive Lumina (Success Patterns)

Extracted from descriptions of `success` entries. When the same approach
appears in 3+ successful expeditions, it becomes an Offensive Lumina.

Format injected into prompt:
```
[OK] Proven approach (Nx successful): <pattern>
```

### Defensive Lumina (Failure Patterns)

Extracted from descriptions of `fail:*` entries. When the same failure
reason appears in 2+ failed expeditions, it becomes a Defensive Lumina.

Format injected into prompt:
```
[WARN] Avoid — failed N times: <pattern>
```

## Extraction Process

1. Read `journal.tsv` (all entries)
2. Group descriptions by status category (success, fail:compile, fail:test, etc.)
3. Extract key phrases from descriptions (normalize whitespace, lowercase)
4. Count occurrences of similar phrases within each category
5. Promote patterns exceeding threshold to Lumina

### Similarity Threshold

Two descriptions are considered "similar" if they share 3+ significant words
(excluding stop words like "add", "fix", "the", "a", etc.).

### Promotion Thresholds

- **Offensive**: 3+ occurrences among `success` entries
- **Defensive**: 2+ occurrences among `fail:*` entries

## Prompt Injection

Before spawning the expedition agent, extract Lumina and prepend to the prompt:

```
## Lumina (Learned Patterns)

### Offensive (Proven Approaches)
[OK] Proven approach (3x successful): add guard clause for nil check
[OK] Proven approach (4x successful): use table-driven test pattern

### Defensive (Known Pitfalls)
[WARN] Avoid — failed 2 times: modifying shared state without mutex
[WARN] Avoid — failed 3 times: changing function signature in public API

### Recent Failure Context
Last 3 failures:
- fail:compile — missing import after refactor
- fail:test — assertion on floating point equality
- fail:compile — type mismatch in interface implementation
```

If no patterns meet the threshold, inject:
```
## Lumina: No patterns detected yet. First expeditions build the knowledge base.
```

## Script Usage

Extract Lumina patterns from journal:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-lumina.py journal.tsv
```

Output is JSON with `offensive` and `defensive` arrays plus `recent_failures`.

## Writing Lumina to File

Optionally write extracted Lumina to `lumina.md` for cross-tool observability:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-lumina.py journal.tsv --output lumina.md
```
