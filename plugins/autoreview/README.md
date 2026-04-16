# autoreview

Autonomous code review plugin powered by [guardrails/semgrep](../../guardrails/semgrep/) rules.

## Modes

### scan-fix

Scans existing code with Semgrep (116 rules across 11 categories), auto-fixes violations,
and validates each fix via git-based keep/revert cycles.

**Metric**: Semgrep findings count (fewer = better).

### spec-review

Reviews type definitions, interfaces, and specs before implementation exists.
Uses LLM-as-judge to apply guardrails rules conceptually and improve design quality.

**Metric**: LLM quality score based on guardrails principles.

## Supported Languages

Go, Python, TypeScript

## Prerequisites

- [Semgrep](https://semgrep.dev/) installed (`semgrep` on PATH)
- `guardrails/semgrep` submodule initialized in the repository

## Usage

```
/review                    # Interactive setup
/review apr16-naming       # Start with tag
```

## Rule Categories (11)

naming, type-safety, immutability, encapsulation, structure, complexity,
layer-dependency, repository, error-handling, security, backward-compat
