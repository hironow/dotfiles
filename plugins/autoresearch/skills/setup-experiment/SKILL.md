---
name: setup-experiment
description: >
  This skill should be used when the user asks to "set up an experiment",
  "initialize a research run", "create experiment config", "prepare experiment branch",
  or needs to configure the autoresearch experiment environment before starting
  an autonomous optimization loop.
version: 0.1.0
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
---

# Experiment Setup

Initialize the autoresearch experiment environment: create branch, config,
results file, and run baseline measurement.

## Setup Checklist

Execute these steps in order before starting the experiment loop:

### 1. Agree on Experiment Tag

Propose a tag based on today's date and purpose (e.g., `mar19-perf-opt`).
Confirm the branch name `experiment/<tag>` does not already exist.

### 2. Create Experiment Branch

```bash
git checkout -b experiment/<tag>
```

### 3. Create experiment-config.yaml

Create `experiment-config.yaml` at the project root with all required fields:

```yaml
tag: "<tag>"
target_files:
  - "path/to/target.py"
eval_command: "just test"          # or custom evaluation command
metric_name: "score"
metric_direction: "lower"          # "lower" or "higher" is better
timeout_seconds: 120
results_file: "results.tsv"
baseline_description: "initial baseline"
```

Request each field value from the user if not obvious from context.

### 4. Initialize results.tsv

Create results file with header only:

```bash
printf 'commit\tmetric\tstatus\tdescription\n' > results.tsv
```

Add to `.gitignore` if not already present:

```bash
grep -q 'results.tsv' .gitignore 2>/dev/null || echo 'results.tsv' >> .gitignore
```

### 5. Read Scope Files

Read all target files and evaluation harness files to build full understanding
of the codebase before experimenting. Identify:
- What can be changed (target files)
- What must not be changed (evaluation, config, dependencies)
- Current architecture and patterns
- Available dependencies and tools

### 6. Run Baseline

Execute the evaluation command and record the baseline:

```bash
<eval_command> > run.log 2>&1
grep "^<metric_name>:" run.log
```

Record in results.tsv:

```bash
printf '%s\t%s\tkeep\tbaseline\n' "$(git rev-parse --short HEAD)" "<metric_value>" >> results.tsv
```

### 7. Confirm and Go

Present setup summary to the user:
- Branch name
- Target files
- Evaluation command and metric
- Baseline metric value
- Time budget per experiment

Once confirmed, hand off to the research-loop skill or researcher agent.

## Validation

Before proceeding, verify:
- [ ] Experiment branch created and checked out
- [ ] experiment-config.yaml exists and is valid
- [ ] results.tsv initialized with header
- [ ] results.tsv is in .gitignore
- [ ] Baseline run completed successfully
- [ ] Baseline metric recorded in results.tsv
- [ ] All scope files read and understood
