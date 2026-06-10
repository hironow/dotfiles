# Project Structure

Read this when creating directories/files or when unsure where something goes.

Standard directories exist **once**, at the repository root. They must not be
duplicated in subdirectories. External dependencies (submodules, cloned repos)
are exempt.

## Root directories

| path            | purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `docs/`         | current-implementation docs + ADRs                            |
| `experiments/`  | research, preliminary experiments, exploratory implementations|
| `output/`       | generated artifacts and build outputs                         |
| `examples/`     | usage examples and sample code                                |
| `scripts/`      | development and utility scripts                               |
| `tests/`        | all test code (unit, integration, e2e, scenario)              |
| `docker/`       | *(optional)* Dockerfiles — only when there are ≥2 (see below) |
| `.semgrep/`     | *(optional)* project-specific Semgrep rules                   |

## Root files

| path            | purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `justfile`      | task runner config (required, exactly one, at root)           |
| `pyproject.toml`| Python project config incl. ruff settings                     |
| `compose.yaml`  | Docker Compose file (when Docker is used)                     |

## Docker layout

- **One** Dockerfile → keep it at the repo root as `Dockerfile`.
- **Two or more** → create `docker/` at the root and put all inside
  (`docker/api.Dockerfile`, `docker/worker.Dockerfile`, …).
- `compose.yaml` stays at the root regardless, referencing `docker/*.Dockerfile`
  via `build.dockerfile`.

```
# single-service           # multi-service
Dockerfile                  docker/
compose.yaml                  api.Dockerfile
                              worker.Dockerfile
                              migration.Dockerfile
                            compose.yaml
```

## docs/ subdirectories

- `docs/adr/` — Architecture Decision Records (see docs/agents/docs-discipline.md).

## tests/ subdirectories

`tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/runn/` (scenario
`*.yaml`), `tests/utils/` (only importable test location). See
docs/agents/testing.md.

## scripts/ rules

- Shebang `#!/usr/bin/env bash` for portability.
- Scripts must be idempotent.
- Process arguments early.
- Prefer defining common tasks in the `justfile` over standalone scripts.
- Optimize for: standardization & error prevention, developer experience,
  idempotency, and clear guidance for the next action.

## experiments/ layout

```
experiments/README.md                              # overview + index table
experiments/YYYY-MM-DD_{name}.md                   # experiment plan
experiments/run_{name}_benchmark.sh                # benchmark script
experiments/test_{name}.py                         # experiment test
```

Experiment doc header: Date, Objective, Status (🟢 Complete / 🟡 In Progress /
⚪ Not Started). Body: Background, Hypothesis, Experiment Design, Expected
Results, Results, Conclusion.

Generated output naming (required: experiment-variable id; recommended:
resolution, step count, guidance scale, other params):

```
preprocessed/{experiment_note_name}/{resolution}/
output/{experiment_note_name}/sage_attention_720p_steps20_cfg5.0.mp4
```

Keep the `experiments/README.md` index updated; summary results there are
reference-only — always check the full note. Organize by status: Complete /
In Progress / Planned.
