---
name: design
description: >
  This skill should be used when the user asks to "start design exploration",
  "run autonomous design", "explore design variations", "optimize my design",
  "begin design loop", "run autodesign", or needs to start or resume
  an autonomous web design exploration loop. This is the top-level entry point
  that orchestrates setup and loop execution. For internal keep/revert
  methodology, see the design-loop skill.
version: 0.1.0
argument-hint: "[design tag or config path]"
allowed-tools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
  - Agent
---

# /design Command

Start an autonomous web design exploration loop.

## Invocation

```
/design              # Interactive setup
/design cafe-top     # Start with tag "cafe-top"
```

## Workflow

### If no design-config.yaml exists

1. Invoke the setup-design skill to initialize the environment
2. Guide the user through configuration
3. Run baseline evaluation
4. Begin the exploration loop

### If design-config.yaml exists

1. Read the config and validate all fields
2. Check git branch state (create or resume `design/<tag>` branch)
3. Read design-results.tsv to understand current progress
4. Determine the current best composite_score from previous runs
5. Launch the designer agent to continue the exploration loop

### Initial Generation (when initial_prompt is set)

When `initial_prompt` is present in config and target files do not yet exist:

1. Generate initial design from the prompt
2. Commit: `design(baseline): initial generation from prompt`
3. Run eval_command to establish baseline composite_score
4. Record baseline in design-results.tsv: `status=keep, axis=baseline`
5. Enter normal exploration loop

### Launching the Loop

Spawn the designer agent via the Agent tool:

```
Agent(
  prompt="Run the next design exploration iteration. Config: <config>. Current best: <score>.",
  name="designer"
)
```

The designer agent is defined in `${CLAUDE_PLUGIN_ROOT}/agents/designer.md`.

For continuous operation, launch multiple sequential iterations.
Each agent invocation handles one exploration cycle (hypothesize, modify, evaluate, decide).

### Resuming

If design-results.tsv has existing entries, resume from the current git state.
Report progress so far before continuing.

## Configuration Reference

See `design-config.yaml` fields:

- `tag` — branch name suffix (`design/<tag>`)
- `target_files` — files the designer may modify
- `eval_target` — URL or file path to evaluate
- `eval_command` — evaluation command
- `initial_prompt` — optional prompt for initial generation
- `evaluators` — which evaluators to use and their weights
- `constraints` — quality floor thresholds
- `exploration_axes` — design dimensions to explore
