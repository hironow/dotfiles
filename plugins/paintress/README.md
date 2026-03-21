# paintress

Claude Code plugin that autonomously picks Linear issues, implements TDD fixes, and creates PRs — with adaptive difficulty, learning from past expeditions, and automated code review.

## Overview

Replaces the original paintress CLI's expedition loop with a pure Claude Code plugin. Instead of a separate binary orchestrating API calls, Claude Code itself executes the full fix cycle natively.

Key game mechanics from the original CLI are preserved:

- **Gradient Gauge**: Momentum system (level 0–5) that scales issue difficulty based on consecutive success/failure
- **Lumina**: Learned patterns extracted from past journals — proven approaches and known pitfalls
- **Review Gate**: Automated post-PR code review with up to 3 fix cycles
- **Gommage**: Fail-safe that halts after 3 consecutive failures or skips

## Quick Start

```bash
# Install the plugin
claude --plugin-dir /path/to/paintress

# Set up expedition target
/expedition

# Or with a tag
/expedition bug-fixes-r1
```

## Entry Points

| Skill | Invocation | Description |
|-------|------------|-------------|
| expedition | `/paintress:expedition [tag]` | Start or resume expedition loop |
| review-journal | `/paintress:review-journal [file]` | Analyze expedition results |

## Components

| Type | Count | Details |
|------|-------|---------|
| **Skills** | 7 | expedition, expedition-loop, setup-continent, review-journal, gradient-gauge, lumina, review-gate |
| **Agent** | 1 | expedition agent (sonnet, autonomous single-issue fixer) |
| **Hook** | 1 | PreToolUse scope guard |
| **Scripts** | 3 | gradient.py, extract-lumina.py, parse-journal.py |

## Prerequisites

- Linear MCP server configured (`mcp__plugin_linear_linear__*` tools available)
- Test runner for the target language (test command is configurable)
- GitHub CLI (`gh pr create` must work)
- Target repository with passing tests

## Configuration

`continent-config.yaml` (created by `/expedition` on first run):

```yaml
tag: "bug-fixes-r1"
repository: "/path/to/your/repository"
branch_prefix: "fix/"
linear_project: "tap next-001"
linear_label: "Bug"
test_command: "make test"
max_expeditions: 10
review_cmd: ""                    # Optional: command for Review Gate
journal_file: "journal.tsv"
```

## Game Mechanics

### Gradient Gauge (Momentum)

Tracks expedition momentum on a 0–5 scale. Affects which issues get selected.

| Level | Name | Behavior |
|-------|------|----------|
| 0 | Depleted | Only low-priority, small-scope issues |
| 1 | Warming | Low to normal priority |
| 2 | Steady | Normal priority |
| 3 | Rising | Normal to high priority |
| 4 | Surging | High priority OK |
| 5 | Gradient Attack | Attempt the most complex issue available |

- **Success** → level + 1 (charge)
- **Skip** → level - 1 (decay)
- **Failure** → level = 0 (discharge)

### Lumina (Learned Patterns)

Extracts patterns from past journals and injects them into the agent prompt:

- **Offensive** (3+ successes): `[OK] Proven approach: <pattern>`
- **Defensive** (2+ failures): `[WARN] Avoid: <pattern>`
- **Recent failures**: Last 3 failure descriptions for context

### Review Gate

After a successful PR, optionally runs `review_cmd`:

1. Run review command → check exit code
2. If issues found → re-spawn agent to fix → push → re-review
3. Up to 3 cycles, then mark as `success:review-pending`

### Gommage (Fail-safe)

3 consecutive failures OR 3 consecutive skips → **HALT**. Writes `gommage.md` with failure analysis and stops the loop.

## State Files

All git-untracked, in the same directory as `continent-config.yaml`:

| File | Purpose |
|------|---------|
| `journal.tsv` | Expedition results (append-only) |
| `gradient.json` | Gradient Gauge state |
| `lumina.md` | Extracted Lumina patterns (optional) |
| `gommage.md` | Failure escalation insight |

## Journal

`journal.tsv` tracks all expedition results:

```
issue	commit	status	pr_url	description
MY-473	51b52b7	success	https://...	#123 partial axes handling
```

Status values: `success`, `success:review-pending`, `fail:compile`, `fail:test`, `fail:timeout`, `skip:no-dod`, `skip:conflict`, `partial:no-pr`
