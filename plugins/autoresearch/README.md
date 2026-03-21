# autoresearch

Autonomous experiment loop plugin for Claude Code, inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch).

Iteratively modifies target code, evaluates against fixed metrics, and keeps only improvements via git-based keep/revert cycles.

## How It Works

```
LOOP:
  1. Form hypothesis
  2. Modify target file(s)
  3. git commit
  4. Run evaluation (with timeout)
  5. Extract metric
  6. Keep if improved, revert if not
  7. Log result to results.tsv
  8. Repeat
```

## Components

| Component | Type | Purpose |
|-----------|------|---------|
| research-loop | Skill | Core experiment loop knowledge |
| setup-experiment | Skill | Experiment initialization |
| analyze-results | Skill | Results analysis and insights |
| /research | Command (Skill) | Start experiment loop |
| /analyze-results | Command (Skill) | Analyze experiment results |
| researcher | Agent | Autonomous experiment subagent |
| PreToolUse guard | Hook | Warn on out-of-scope file edits |

## Quick Start

### 1. Install

```bash
claude --plugin-dir /path/to/plugins/autoresearch
```

### 2. Setup

```
/research my-experiment
```

This creates `experiment-config.yaml`, initializes `results.tsv`, and runs the baseline.

### 3. Run

The researcher agent autonomously runs experiments. Each cycle:
- Modifies only designated target files
- Evaluates against the fixed metric
- Keeps improvements, reverts failures
- Logs everything to results.tsv

### 4. Analyze

```
/analyze-results
```

View experiment progress, keep rate, improvement trajectory, and recommendations.

## Configuration

Create `experiment-config.yaml` in your project root:

```yaml
tag: "experiment-name"
target_files:
  - "src/algorithm.py"
eval_command: "just test"
metric_name: "score"
metric_direction: "lower"    # "lower" or "higher" is better
timeout_seconds: 120
results_file: "results.tsv"
```

## Use Cases

- Code performance optimization (execution time, memory)
- Hyperparameter tuning (model training, config optimization)
- Prompt engineering (evaluation score optimization)
- Test coverage improvement
- Bundle size optimization

## Design Principles

From the original autoresearch:

1. **Immutable evaluation**: Evaluation harness is never modified
2. **Single target**: Only designated files are changed per experiment
3. **Fixed budget**: Each experiment runs within a time/resource budget
4. **Simplicity criterion**: Reject complex code for marginal gains
5. **Append-only log**: All results preserved regardless of keep/revert
