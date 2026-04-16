---
name: setup-review
description: >
  This skill should be used when the user asks to "set up a review",
  "initialize code review", "create review config", "prepare review branch",
  "configure autoreview", or needs to set up the autoreview environment before
  starting an autonomous code review loop.
version: 0.1.0
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
---

# Review Setup

Initialize the autoreview environment: create branch, config, results file,
and run baseline Semgrep scan.

## Setup Checklist

Execute these steps in order before starting the review loop.

### 1. Verify Prerequisites

Check that Semgrep is installed and guardrails rules are accessible:

```bash
semgrep --version
bash "${CLAUDE_PLUGIN_ROOT}/scripts/resolve-guardrails.sh"
```

If `resolve-guardrails.sh` fails, prompt the user to initialize the
`guardrails/semgrep` submodule.

### 2. Agree on Review Tag

Propose a tag based on today's date and focus area (e.g., `apr16-naming-fix`).
Confirm the branch name `review/<tag>` does not already exist.

### 3. Select Review Mode

Ask the user which mode to use:

- **scan-fix**: Existing code with Semgrep violations to fix. Metric = findings count.
- **spec-review**: Type definitions, interfaces, or specs without full implementation.
  Metric = LLM quality score (1-10) based on guardrails principles.

### 4. Create Review Branch

```bash
git checkout -b review/<tag>
```

### 5. Create review-config.yaml

Create `review-config.yaml` at the project root:

```yaml
tag: "<tag>"
mode: "scan-fix"                    # "scan-fix" or "spec-review"
target_paths:
  - "src/"
rule_categories: []                 # empty = all categories
languages: []                       # empty = all (go, python, typescript)
guardrails_path: ""                 # auto-resolved at runtime
results_file: "review-results.tsv"
timeout_seconds: 120
max_iterations_per_category: 5      # prevent infinite loops
max_consecutive_no_improvement: 2   # skip category after N stalls
```

Request each field value from the user. For `rule_categories`, present the
available categories: naming, type-safety, immutability, encapsulation,
structure, complexity, layer-dependency, repository, error-handling, security,
backward-compat.

### 6. Initialize review-results.tsv

```bash
printf 'commit\tmode\tcategory\tfile\tfindings_before\tfindings_after\tstatus\tdescription\n' > review-results.tsv
```

Add to `.gitignore` if not already present:

```bash
grep -q 'review-results.tsv' .gitignore 2>/dev/null || echo 'review-results.tsv' >> .gitignore
```

### 7. Run Baseline Scan

For **scan-fix** mode, run Semgrep and record the baseline:

```bash
RULES=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/resolve-guardrails.sh")
semgrep --config "$RULES" --json <target_paths> > review-scan.json 2>/dev/null
```

Count total findings and record per-category breakdown.

For **spec-review** mode, read the target files and perform an initial
LLM-based quality assessment against guardrails principles.

### 8. Confirm and Go

Present setup summary:
- Branch name and mode
- Target paths and rule categories
- Baseline findings count (scan-fix) or quality score (spec-review)
- Loop limits (max iterations, stall threshold)

Once confirmed, hand off to the review skill or reviewer agent.

## Validation

Before proceeding, verify:
- [ ] Semgrep is installed and rules are accessible
- [ ] Review branch created and checked out
- [ ] review-config.yaml exists and is valid
- [ ] review-results.tsv initialized with header
- [ ] Baseline scan or assessment completed
- [ ] All target files read and understood
