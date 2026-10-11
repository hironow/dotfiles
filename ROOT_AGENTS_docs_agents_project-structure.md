# Project structure

Read this when you create directories or files, or when you are not sure where
something goes.

Each standard directory exists **once**, at the repository root. Do not
duplicate it in a subdirectory. External dependencies (submodules, cloned
repos) are exempt.

## Root directories

| path            | purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `docs/`         | current-implementation docs + ADRs                            |
| `experiments/`  | research, preliminary experiments, exploratory implementations|
| `output/`       | generated artifacts and build outputs                         |
| `examples/`     | usage examples and sample code                                |
| `scripts/`      | development and utility scripts                               |
| `fake/`         | in-memory fakes of external services, one per driven port (docs/agents/core-shell-ports.md) |
| `docker/`       | *(optional)* Dockerfiles — only when there are ≥2 (see below) |
| `.semgrep/`     | *(optional)* project-specific Semgrep rules                   |

## Root files

| path            | purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `justfile`      | task runner config (required, exactly one, at root)           |
| `pyproject.toml`| Python project config incl. ruff settings                     |
| `compose.yaml`  | Docker Compose file (when Docker is used)                     |

## Docker layout

- **One** Dockerfile: keep it at the repo root as `Dockerfile`.
- **Two or more**: create `docker/` at the root and put them all there
  (`docker/api.Dockerfile`, `docker/worker.Dockerfile`, …).
- `compose.yaml` always stays at the root. It points to `docker/*.Dockerfile`
  with `build.dockerfile`.

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

## scripts/ rules

- Keep `#!/usr/bin/env bash` as the shebang of Bash scripts, for portability.
  Write a new executable tool in Go (Rust when Go does not fit), not in shell
  (docs/agents/go-tooling.md).
- Make scripts idempotent.
- Process arguments early.
- Prefer defining common tasks in the `justfile` over standalone scripts.
