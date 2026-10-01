# tests/

Pytest suites that run against the dev container image and the
exe.hironow.dev IaC. Tests use real Docker / file system / git;
no mocks of project code.

## Layout

| Path | Purpose |
|---|---|
| [`test_devcontainer.py`](./test_devcontainer.py) | Dev container image runtime smoke (`mise current`, `MISE_DATA_DIR`, AI CLI `--version`) |
| [`unit/test_install_os_dispatch.py`](./unit/test_install_os_dispatch.py) | `install.sh` OS dispatch contract (uname → DOTFILES_OS, `step_*` helpers) |
| [`unit/test_mise_data_dir_relocation.py`](./unit/test_mise_data_dir_relocation.py) | `MISE_DATA_DIR=/opt/mise` invariant across 3 files |
| [`unit/test_justfile_windows_subset.py`](./unit/test_justfile_windows_subset.py) | `deploy` / `clean` Windows native cross-platform subset (ADR 0018) |
| [`unit/test_justfile_env_checks.py`](./unit/test_justfile_env_checks.py) | `${VAR:?msg}` env guards actually fire in shebang recipes (`$$` does not) |
| [`test_just_sandbox.py`](./test_just_sandbox.py) | `just <recipe>` end-to-end inside the dev container |
| [`test_sync_agents.py`](./test_sync_agents.py) | `just sync-agents` (Claude / Gemini / Codex agent file mirroring) |
| [`unit/`](./unit/) | Host-only tests, no Docker: pure-Python helpers and static checks of files (`just test-unit`, part of `just ci`) |
| [`docker/`](./docker/) | Dockerfiles the heavier suites build (`InstallTest.Dockerfile` for `just test-install`) |
| [`e2e/exe/`](./e2e/exe/) | The exe stack's stop paths against the real cluster; skipped unless `EXE_E2E=1` (`just exe-e2e`, see its README) |

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
