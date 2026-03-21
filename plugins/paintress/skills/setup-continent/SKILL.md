---
name: setup-continent
description: >-
  This skill should be used when initializing a paintress expedition
  environment for the first time, setting up "continent-config.yaml",
  or when the user asks to "set up expedition", "initialize continent",
  "configure expedition target", "create expedition config",
  "configure paintress", or "first time setup".
  Works with any language — test command is configurable.
version: 0.2.0
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
  - mcp__plugin_linear_linear__list_issues
---

# Setup Continent — Expedition Initialization

Initialize the expedition environment by creating `continent-config.yaml` and `journal.tsv`.

## Initialization Steps

### 1. Gather Configuration

Ask the user for each required field (provide defaults where possible):

| Field | Question | Default |
|-------|----------|---------|
| `tag` | Expedition tag for branch naming? | `expedition-r1` |
| `repository` | Absolute path to target repository? | (must provide) |
| `branch_prefix` | Branch name prefix? | `fix/` |
| `linear_project` | Linear project name? | (must provide) |
| `linear_label` | Label filter for issues? | `Bug` |
| `test_command` | Command to run tests? | (must provide) |
| `max_expeditions` | Max issues per session? | `10` |
| `review_cmd` | Command to review PRs (empty to skip, see review-gate skill)? | `""` |

### 2. Validate Inputs

Before writing config:
- Verify `repository` exists: `ls <repository>`
- Verify `test_command` works: `cd <repository> && <test_command> 2>&1 | tail -5`
- Verify Linear project exists: `list_issues(project=<linear_project>, limit=1)`
- Verify label exists: check that at least 1 issue matches the label filter

### 3. Write continent-config.yaml

```yaml
tag: "<tag>"
repository: "<absolute-path>"
branch_prefix: "<prefix>"
linear_project: "<project-name>"
linear_label: "<label>"
test_command: "<command>"
max_expeditions: <number>
review_cmd: "<command or empty>"
journal_file: "journal.tsv"
```

Write to the current working directory (where `/expedition` is invoked).

### 4. Initialize journal.tsv

Create with header only:

```
issue	commit	status	pr_url	description
```

Add the following to `.gitignore` if not already present (state files created during expeditions):
- `journal.tsv` — expedition results log
- `gradient.json` — Gradient Gauge momentum state
- `lumina.md` — extracted learning patterns
- `gommage.md` — failure escalation insight

### 5. Verify Baseline

Run the test command once to confirm the repository is in a clean state:

```bash
cd <repository> && <test_command>
```

If tests fail, warn the user and do not proceed until baseline passes.

### 6. Present Summary

```
Expedition configured:
  Repository: /path/to/your/repository
  Linear:     tap next-001 (Bug label)
  Tests:      <test_command>
  Max:        10 expeditions
  Journal:    journal.tsv (initialized)
  Baseline:   PASS

Run /expedition to start.
```
