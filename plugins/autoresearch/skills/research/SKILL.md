---
name: research
description: >
  This skill should be used when the user asks to "start research",
  "run autonomous experiments", "optimize my code automatically",
  "begin experiment loop", "run autoresearch", or needs to start or resume
  an autonomous research experiment loop. This is the top-level entry point
  that orchestrates setup and loop execution. For internal keep/revert
  methodology, see the research-loop skill.
version: 0.1.0
argument-hint: "[experiment tag or config path]"
allowed-tools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
  - Agent
---

# /research Command

Start an autonomous research experiment loop.

## Invocation

```
/research              # Interactive setup
/research mar19-perf   # Start with tag "mar19-perf"
```

## Workflow

### If no experiment-config.yaml exists

1. Invoke the setup-experiment skill to initialize the environment
2. Guide the user through configuration
3. Run baseline
4. Begin the experiment loop

### If experiment-config.yaml exists

1. Read the config and validate all fields
2. Check git branch state (create or resume experiment branch)
3. Read results.tsv to understand current progress
4. Determine the current best metric from previous runs
5. Launch the researcher agent to continue the experiment loop

### Launching the Loop

Spawn the researcher agent via the Agent tool:

```
Agent(
  prompt="Run the next experiment iteration. Config: <config>. Current best: <metric>.",
  name="researcher"
)
```

The researcher agent is defined in `${CLAUDE_PLUGIN_ROOT}/agents/researcher.md`.

For continuous operation, launch multiple sequential experiments.
Each agent invocation handles one experiment cycle (modify, run, evaluate, decide).

### Resuming

If results.tsv has existing entries, resume from the current git state.
Report progress so far before continuing.
