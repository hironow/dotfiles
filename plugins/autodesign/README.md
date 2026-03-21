# autodesign

Autonomous web design exploration plugin for Claude Code.

Iteratively explores design variations under quality constraints using git-based keep/revert cycles, inspired by [autoresearch](../autoresearch/).

## How It Works

```
LOOP:
  1. Form design hypothesis (select exploration axis)
  2. Modify target file(s)
  3. git commit
  4. Run evaluation (with timeout)
  5. Check quality constraints (immediate revert if violated)
  6. Compare composite_score (keep if improved, revert if not)
  7. Log result to design-results.tsv
  8. Repeat
```

## Components

| Component | Type | Purpose |
|-----------|------|---------|
| design-loop | Skill | Core exploration loop knowledge |
| setup-design | Skill | Exploration initialization |
| analyze-results | Skill | Results analysis and insights |
| /design | Command (Skill) | Start exploration loop |
| /analyze-results | Command (Skill) | Analyze exploration results |
| designer | Agent | Autonomous exploration subagent |
| PreToolUse guard | Hook | Warn on out-of-scope file edits |
| evaluators/* | Scripts | Bundled quality evaluators |
| eval-composite.sh | Script | Evaluation orchestrator |
| parse-results.py | Script | Results parser |

## Quick Start

### 1. Install

```bash
claude --plugin-dir /path/to/plugins/autodesign
```

### 2. Setup

```
/design my-redesign
```

This creates `design-config.yaml`, initializes `design-results.tsv`, and runs the baseline.

### 3. Run

The designer agent autonomously explores design variations. Each cycle:
- Selects an exploration axis (layout, color, typography, etc.)
- Modifies only designated target files
- Evaluates against quality constraints
- Keeps improvements, reverts failures
- Logs everything to design-results.tsv

### 4. Analyze

```
/analyze-results
```

View exploration progress, axis performance, constraint violations, and recommendations.

## Configuration

Create `design-config.yaml` in your project root:

```yaml
tag: "experiment-name"
target_files:
  - "src/app/page.tsx"
eval_target: "http://localhost:3000"
eval_command: "bash ${CLAUDE_PLUGIN_ROOT}/scripts/eval-composite.sh"
metric_name: "composite_score"
metric_direction: "higher"
timeout_seconds: 90
results_file: "design-results.tsv"

# Optional: generate initial design from prompt
# initial_prompt: "Modern cafe page, Tailwind CSS, Japanese, mobile-first"

evaluators:
  structure:
    enabled: true
    weight: 0.30
  readability:
    enabled: true
    weight: 0.20
  lighthouse:
    enabled: true
    weight: 0.30
  completeness:
    enabled: true
    weight: 0.20

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

## Bundled Evaluators

| Evaluator | Metric | Chrome Required |
|-----------|--------|-----------------|
| structure.sh | Pa11y a11y errors | Yes |
| readability.sh | AEO score (0-100) | No |
| lighthouse.sh | Lighthouse average (0-100) | Yes |
| completeness.sh | Placeholder detection (0-100) | No |
| html-validate.sh | HTML validation errors | No |

## Design Principles

1. **Exploratory, not diagnostic**: Explore design variations, don't just fix issues
2. **Quality as constraint**: Metrics are floors (constraints), not optimization targets
3. **Immutable evaluation**: Evaluation harness is never modified
4. **Single target**: Only designated files are changed per iteration
5. **Fixed budget**: Each iteration runs within a time budget
6. **Append-only log**: All results preserved regardless of keep/revert

## Dependencies

Required: Node.js, Git
Optional: Chrome/Chromium (for structure.sh, lighthouse.sh), yq (for YAML parsing)
