---
name: review
description: >
  This skill should be used when the user asks to "start a review",
  "run autoreview", "review my code", "fix semgrep violations",
  "review specs", "review types", "begin review loop", or needs to start
  or resume an autonomous code review loop. This is the top-level entry
  point that orchestrates setup and loop execution.
version: 0.1.0
argument-hint: "[review tag or config path]"
allowed-tools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
  - Agent
---

# /review Command

Start an autonomous code review loop.

## Invocation

```
/review                    # Interactive setup
/review apr16-naming       # Start with tag "apr16-naming"
```

## Workflow

### If no review-config.yaml exists

1. Invoke the setup-review skill to initialize the environment
2. Guide the user through mode selection and configuration
3. Run baseline scan
4. Begin the review loop

### If review-config.yaml exists

1. Read the config and validate all fields
2. Check git branch state (create or resume review branch)
3. Read review-results.tsv to understand current progress
4. Resolve guardrails path:

   ```bash
   RULES=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/resolve-guardrails.sh")
   ```

5. Determine which categories still need work
6. Launch the reviewer agent to continue the review loop

### Determining Next Category

Read review-results.tsv and apply these rules:

1. Skip categories that reached `max_iterations_per_category`
2. Skip categories with `max_consecutive_no_improvement` stalls in a row
3. Pick the category with the highest remaining findings count
4. If all categories are done or skipped, report completion

### Launching the Loop

Spawn the reviewer agent via the Agent tool:

```
Agent(
  prompt="Run the next review iteration. Config: <config>. Mode: <mode>. Category: <category>. Current findings: <count>. Rules path: <rules_path>.",
  name="reviewer"
)
```

The reviewer agent is defined in `${CLAUDE_PLUGIN_ROOT}/agents/reviewer.md`.

Each agent invocation handles one review cycle (scan, analyze, fix, rescan, decide).
After each cycle, check if the loop should continue or stop.

### Loop Termination

Stop the loop when any of these conditions are met:

- All categories completed or skipped
- Zero findings remaining (scan-fix mode)
- Quality score reaches 9+ for all files (spec-review mode)
- User interrupts

### Resuming

If review-results.tsv has existing entries, resume from the current git state.
Report progress so far (categories done, findings fixed, remaining) before continuing.

## Related Skills

- **review-loop**: Internal keep/revert methodology and decision logic.
  The reviewer agent consults `review-loop/references/decision-logic.md`
  for the full decision matrix.
- **setup-review**: Environment initialization (invoked automatically if
  no review-config.yaml exists).
- **analyze-results**: Post-loop results analysis and summary.
