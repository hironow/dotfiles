---
name: expedition
description: >-
  Entry point for the paintress plugin. This skill should be used when
  the user asks to "run an expedition", "pick a Linear issue and fix it",
  "start fixing bugs", "autonomous TDD loop", "/expedition", or wants to
  automatically implement Linear issues with TDD and create PRs. Also
  applicable when the user mentions "paintress plugin" or "autonomous fix cycle".
  For core TDD cycle reference, see the expedition-loop skill.
version: 0.2.0
argument-hint: "[tag] or empty for interactive setup"
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "mcp__plugin_linear_linear__list_issues", "mcp__plugin_linear_linear__save_issue", "mcp__plugin_linear_linear__get_issue"]
---

# Expedition — Autonomous TDD Fix Loop

Entry point for the paintress expedition plugin. Pick Linear issues, implement fixes via TDD, and create PRs autonomously. Incorporates Gradient Gauge momentum, Lumina learning, and Review Gate quality checks.

## Workflow

### If `continent-config.yaml` does NOT exist

Invoke the `setup-continent` skill to initialize the expedition environment. Do not proceed until config is created.

### If `continent-config.yaml` exists

#### Phase 1: Pre-flight

1. Read `continent-config.yaml` for target repository, Linear project, test command, and label filter
2. **Read Gradient Gauge state**:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gradient.py read gradient.json
   ```

   - If `gommage: true` → **HALT**. Report gommage condition to user (3+ consecutive failures or skips). Do NOT start any expeditions. Show recent failures and suggest corrective actions.
3. **Extract Lumina patterns**:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-lumina.py journal.tsv
   ```

   Save the JSON output for prompt injection.
4. Read `journal.tsv` to identify already-processed issues (skip them)

#### Phase 2: Issue Selection

5. Query Linear MCP: `list_issues(project=<linear_project>, label=<linear_label>, state="Backlog")`
6. Filter out issues already in journal.tsv (by issue ID)
7. If no remaining issues: report "All issues processed" and exit
8. **Apply Gradient priority filter** — see gradient-gauge skill for full level-to-priority mapping
9. Select the top issue after filtering

#### Phase 3: Expedition Execution

10. Spawn the **expedition agent** (defined in `${CLAUDE_PLUGIN_ROOT}/agents/expedition.md`) with full context:

```
Agent(
  subagent_type="paintress:expedition",
  prompt="Execute expedition for issue <ID>: <title>

Description:
<description>

Config: <config contents>
Repository: <repository path>
Test command: <test_command>
Branch prefix: <branch_prefix>

Gradient Gauge: Level <N>/5 (<level_name>)
Priority hint: <priority_hint>

<lumina_markdown>
",
  run_in_background=false
)
```

#### Phase 4: Post-expedition

11. Parse agent result (RESULT, ISSUE, COMMIT, PR, DESCRIPTION)
12. Append result to `journal.tsv`
13. **Update Gradient Gauge**:

    ```bash
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gradient.py update gradient.json <status>
    ```

14. **Review Gate** (if status is "success" AND PR was created AND `review_cmd` is configured):
    - Run `review_cmd` in the worktree directory
    - If exit code non-zero and review cycle < 3:
      - Re-spawn expedition agent with review feedback
      - Agent fixes issues, runs tests, commits, pushes
      - Repeat review
    - If exit code 0: review passed
    - If 3 cycles exhausted: update status to `success:review-pending`
    - See review-gate skill for full details
15. If status is "success", update Linear issue: `save_issue(id=<ID>, state="Done")`
16. Check updated gradient state:
    - If `gommage: true` → **HALT** and report
    - If `max_expeditions` not reached → repeat from Phase 2

## Configuration Reference

See `continent-config.yaml` format in the `setup-continent` skill.

## Journal Format

Tab-separated, git-untracked, append-only:

```
issue commit status pr_url description
```

Status values: `success`, `success:review-pending`, `fail:compile`, `fail:test`, `fail:timeout`, `skip:no-dod`, `skip:conflict`, `partial:no-pr`

## State Files

All in the same directory as `continent-config.yaml`, all git-untracked:

| File | Purpose |
|---|---|
| `journal.tsv` | Expedition results log |
| `gradient.json` | Gradient Gauge momentum state |
| `lumina.md` | Extracted Lumina patterns (optional) |
| `gommage.md` | Failure escalation insight (written on gommage) |

## Continuous Operation

For continuous expedition runs, invoke `/expedition` repeatedly or specify a high `max_expeditions` in config. Each invocation resumes from where the journal left off, with Gradient Gauge and Lumina state preserved across sessions.
