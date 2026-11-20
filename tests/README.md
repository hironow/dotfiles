# tests/

Tests are split by whether they require containers.
They run on Podman 5+ with podman-compose as the Compose provider.

| Location | Contents | Run |
| --- | --- | --- |
| [`unit/`](./unit/) | Container-free function, file, and process boundary tests | `just test-unit` (included in `just ci`) |
| `test_just_sandbox.py`, etc. | Build a dedicated image per run and test real Dev Container up -> exec and saved images | `just test` |
| [`powershell/`](./powershell/) | Tests running on Windows PowerShell 5.1 (how Podman GC parses JSON) | CI `test-podman-gc-compat.yaml` only (5.1 exists only on Windows) |
| `test_install.py` / [`docker/`](./docker/) | Test normal setup twice using a tracked-files-only context and `InstallTest.Dockerfile` | `just test-install` |

Place container-free static tests in `unit/`.
Wire any new tests directly under `tests/` into the run recipes listed in the table.
End-to-end tests against real services and databases live in [`../emulator/tests/e2e/`](../emulator/tests/e2e/).

## Running tests

```bash
just test-unit                         # unit/ only (no containers needed)
just test                              # required sandbox tests
just test-mark validate                # filter by marker (install, validate, versions, deploy, check)
just test-install                      # normal setup twice plus invocation tripwire
uv run --frozen --group dev pytest tests/unit/test_<name>.py  # single file
```

`just test-unit` runs the unit tests in parallel on every CPU (pytest-xdist, `--dist loadgroup`).
A test must be safe to run beside any other: write only under `tmp_path`, change the environment only through `monkeypatch`, and bind no fixed port.
A test that starts its own pytest in the checkout passes `-p no:cacheprovider`, as the run itself does, so no `.pytest_cache` temporary directory appears under another process's collection.
Tests that share a module-scoped fixture they should build once carry the same `@pytest.mark.xdist_group(...)`.
The checkout guard in `unit/conftest.py` runs only in the controlling process.
To debug a test serially, run it with `-n 0` (or run the single file as above).

## Isolated emulator CI-equivalent tests

After linting, `just ci-emu` runs prepare -> start -> wait on Firebase, Spanner, pgadapter, Postgres, and
telemetry using a dedicated manifest, then runs the same non-e2e, e2e, and Postgres 18 tests as CI.
It requires an existing Podman / podman-compose setup and the emulator uv environment; it performs no host installation.
It uses the frozen dev group in `emulator/` and preserves `UV_PROJECT_ENVIRONMENT`, `UV_NO_SYNC`, and
`UV_OFFLINE`. Do not move or invoke any local Docker binary.

It does not start or delete the shared stack, and it rejects an inherited `DOTFILES_PODMAN_RUN_MANIFEST`.
On normal exit or failure, it calls cleanup only for that same manifest. It preserves the original failure and does not treat cleanup failures as success.
Do not delete `.pi/tasks/ci-emu.*/run.json` or its underlying snapshot/tmp directories from the shell.
On INT or TERM, it does not start competing cleanup; it leaves the manifest intact and exits non-zero.
SIGKILL can also leave resources behind. **Once the creator process stops**, clean up the printed manifest from `emulator/` with no concurrent cleanups (never use `emu-clean`):

```bash
uv run --frozen --group dev python -m tests.utils.isolation cleanup --manifest /absolute/path/to/run.json
```

Do not manually mark an in-doubt creation journal as finished, and do not delete snapshots before cleanup.

## Writing conventions

General testing conventions (mocking policy, given / when / then) live in
the [testing spoke](../ROOT_AGENTS_docs_agents_testing.md). Conventions specific to this repository:

- Even unit tests use real files, git, and processes wherever possible. Replace external services (such as gcloud, claude, npm) with stubs on PATH, and limit `monkeypatch` to boundary I/O.
- The legacy fixture names `docker_image` and `saved_image` are kept for compatibility; they resolve to verified immutable Podman image IDs per run.
- `just test` runs from the host using a snapshot of tracked working files only.
  It rejects paths into symlinks, junctions, or Git metadata, and never mounts the real checkout's `.git`.
  A one-off test allows binding a checkout only when `DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1` and a matching engine-side path are set.
  Full up -> exec tests place the snapshot outside real Git ancestry and reject nested Dev Container launches.
- See the [Dev Container guide](../.devcontainer/README.md) for active engine socket and permission details.
  Because the socket grants engine control, do not treat it as an isolated security sandbox.
- Never turn missing required CLIs, connections, builds, or runtime failures into passes via `pytest.skip`.
  Keep creation journals incomplete when termination is unknown, and do not infer completion from an empty inventory alone.
  Limit cleanup to resources and tags recorded and verified by this run; never delete the shared stack or other image aliases.

## Running on Windows

Keep all `unit/` tests passing on native Windows (Japanese locale, cp932).

- Pass `encoding="utf-8"` for text file I/O and `encoding="utf-8", errors="replace"` for subprocess `text=True` (checked by `unit/test_text_io_encoding.py`).
- Pass `newline="\n"` when writing shell stubs (bash cannot read CRLF).
- When launching bash from a native process, use `resolve_bash()` from `unit/_bash_hook.py` and convert PATH entries with `bash_path()` to `/c/...` form.
- Skip only checks that Windows cannot represent, such as POSIX file modes (0600, executable bit).

## Related documentation

- [`../docs/runbook/windows-host.md`](../docs/runbook/windows-host.md): native Windows gotchas
