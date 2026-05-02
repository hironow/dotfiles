# tests/

Pytest suites that run against the dev container image and the
exe.hironow.dev IaC. Tests use real Docker / file system / git;
no mocks of project code.

## Layout

| Path | Purpose |
|---|---|
| [`test_devcontainer.py`](./test_devcontainer.py) | Dev container image runtime smoke (`mise current`, `MISE_DATA_DIR`, AI CLI `--version`) |
| [`test_install_os_dispatch.py`](./test_install_os_dispatch.py) | `install.sh` OS dispatch contract (uname → DOTFILES_OS, `step_*` helpers) |
| [`test_mise_pin_consistency.py`](./test_mise_pin_consistency.py) | `mise.toml` ↔ `feature install.sh` ↔ `/etc/mise/config.toml` drift guard |
| [`test_mise_data_dir_relocation.py`](./test_mise_data_dir_relocation.py) | `MISE_DATA_DIR=/opt/mise` invariant across 4 files |
| [`test_vm_bootstrap.py`](./test_vm_bootstrap.py) | Workspace VM startup_script supply-chain regressions (no curl\|bash, fingerprint pins) |
| [`test_publish_workflow.py`](./test_publish_workflow.py) | `publish-devcontainer.yaml` GHA WIF auth + tag invariants |
| [`test_cdr_wrapper.py`](./test_cdr_wrapper.py) | `exe/scripts/cdr` Secret Manager fetch + cleanup-on-failure |
| [`test_just_sandbox.py`](./test_just_sandbox.py) | `just <recipe>` end-to-end inside the dev container |
| [`test_sync_agents.py`](./test_sync_agents.py) | `just sync-agents` (Claude / Gemini / Codex agent file mirroring) |
| [`exe/test_startup_script.py`](./exe/test_startup_script.py) | Control-plane VM startup_script (heredoc extraction + bash lint + systemd-analyze) |
| [`exe/test_template.py`](./exe/test_template.py) | `exe/coder/templates/...` HCL static checks |
| [`unit/`](./unit/) | Pure-Python helpers (no Docker, no fixtures) |
| [`docker/`](./docker/) | Dockerfiles supporting the heavier exe smoke tests |

## Running

```bash
just test                        # full suite (builds dev container image first)
uvx pytest tests/test_<name>.py  # single file
uvx pytest -m exe                # only `@pytest.mark.exe` (heavy IaC tests)
```

## Authoring conventions

- **No mocks of project code.** External services (gcloud, coder, npm) get real stubs on PATH; project modules run as-is.
- **One container per test.** Use the existing fixtures (`docker_image`, `saved_image`); each test gets a fresh `--rm` container.
- **Given / When / Then** in the test body when setup is non-trivial.
- **Docker required.** Tests that need it call `pytest.skip` when Docker is unreachable so local runs without Docker still pass the rest.

## Related docs

- [`../README.md`](../README.md) — repo overview
- [`../docs/adr/`](../docs/adr/) — decisions the tests guard
- [`../exe/docs/architecture.md`](../exe/docs/architecture.md) — what `tests/exe/` exercises
