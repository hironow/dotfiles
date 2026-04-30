---
name: setup-design
description: >
  This skill should be used when the user asks to "set up a design experiment",
  "initialize a design exploration", "create design config", "prepare design branch",
  or needs to configure the autodesign environment before starting
  an autonomous design exploration loop.
version: 0.1.0
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
---

# Design Exploration Setup

Initialize the autodesign experiment environment: create branch, config,
results file, and run baseline measurement.

## Setup Checklist

Execute these steps in order before starting the exploration loop:

### 1. Agree on Design Tag

Propose a tag based on today's date and purpose (e.g., `mar21-cafe-redesign`).
Confirm the branch name `design/<tag>` does not already exist.

### 2. Create Design Branch

```bash
git checkout -b design/<tag>
```

### 3. Create design-config.yaml

Create `design-config.yaml` at the project root with all required fields:

```yaml
tag: "<tag>"
target_files:
  - "path/to/target.tsx"
eval_target: "http://localhost:3000"    # or file path
eval_command: "bash ${CLAUDE_PLUGIN_ROOT}/scripts/eval-composite.sh"
metric_name: "composite_score"
metric_direction: "higher"
timeout_seconds: 90
results_file: "design-results.tsv"
# Optional: omit to start from existing files
# initial_prompt: "Design description here"
evaluators:
  structure: { enabled: true, weight: 0.30 }
  readability: { enabled: true, weight: 0.20 }
  lighthouse: { enabled: true, weight: 0.30 }
  completeness: { enabled: true, weight: 0.20 }
constraints:
  structure_errors_max: 3
  aeo_score_min: 50
  lighthouse_avg_min: 70
  completeness_score_min: 60
exploration_axes:
  - layout
  - color
  - typography
  - animation
  - spacing
  - imagery
```

Request each field value from the user if not obvious from context.

### 4. Verify eval_target Reachability

For URL targets:

```bash
curl -s -o /dev/null -w "%{http_code}" <eval_target>
```

For file targets:

```bash
test -f <eval_target> && echo "OK" || echo "NOT FOUND"
```

### 5. Check Evaluator Dependencies

For each enabled evaluator, verify dependencies are available:

- **structure** (Pa11y): Requires Chrome/Chromium
- **readability**: Requires Node.js (no Chrome)
- **lighthouse**: Requires Chrome/Chromium
- **completeness**: Requires Node.js (no Chrome)
- **html-validate**: Requires Node.js (no Chrome)

```bash
# Check Chrome availability
which google-chrome || which chromium || echo "Chrome not found"
```

If Chrome is not available, disable structure and lighthouse evaluators and
adjust weights so remaining evaluators sum to 1.0.

### 6. Initialize design-results.tsv

Create results file with header:

```bash
printf 'commit\tcomposite_score\tstatus\tconstraint\taxis\tdescription\n' > design-results.tsv
```

Add to `.gitignore` if not already present:

```bash
grep -q 'design-results.tsv' .gitignore 2>/dev/null || echo 'design-results.tsv' >> .gitignore
```

### 7. Read Scope Files

Read all target files and evaluation config to build full understanding
of the design before exploring. Identify:

- What can be changed (target files)
- What must not be changed (evaluation, config, dependencies)
- Current design patterns and architecture
- Available CSS framework and tools

### 8. Run Baseline (when initial_prompt is NOT set)

When starting from existing files (no `initial_prompt`), execute the evaluation
and record the baseline:

```bash
<eval_command> > run.log 2>&1
grep "^composite_score:" run.log
```

Record in design-results.tsv:

```bash
printf '%s\t%s\tkeep\t-\tbaseline\tinitial design\n' \
  "$(git rev-parse --short HEAD)" "<composite_score>" >> design-results.tsv
```

When `initial_prompt` IS set, skip this step — Step 0 of the core loop handles
initial generation and baseline recording.

### 9. Confirm and Go

Present setup summary to the user:

- Branch name
- Target files
- Evaluation target and command
- Enabled evaluators and their weights
- Constraint thresholds
- Baseline composite_score (if measured)
- Exploration axes

Once confirmed, hand off to the design-loop skill or designer agent.

## Validation

Before proceeding, verify:

- [ ] Design branch created and checked out
- [ ] design-config.yaml exists and is valid
- [ ] eval_target is reachable
- [ ] Evaluator dependencies are available
- [ ] design-results.tsv initialized with header
- [ ] design-results.tsv is in .gitignore
- [ ] Baseline run completed (or initial_prompt set for deferred baseline)
- [ ] All scope files read and understood
