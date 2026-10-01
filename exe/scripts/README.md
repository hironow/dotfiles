# exe/scripts/

Operational scripts for `exe.hironow.dev`.

This README documents the file-level layout.

The retired Coder stack's scripts (`cdr` and its family, `bootstrap.sh`,
`smoke.sh`, `teardown.sh`, the project helpers) went with that stack; the
`ax-*` scripts below are what replaced them. `ax-job` and `ax-exec` still say
"the AX stack's `cdr-job`" because that is the shape they were built to replace,
and a reader coming from the old commands needs the mapping.

## Files

| Path | Purpose |
|---|---|
| [`ax-job`](./ax-job) | The AX stack's `cdr-job`: run one command in a fresh AX task, then delete the task (`just exe-ax-job`). Checks the lease (`exe-reaper may-start`) before anything exists and again right before the launch, tags the digest-pinned image `inuse-<sha12>-<unix>` before the task exists, and deletes the task only once the command's end is certain. AX fails a task that no worker was free for and never retries it (a deleted task holds its worker for a few minutes), so ax-job deletes such a task and applies it again once, 2 minutes later, then says to wait for a worker. `--claude` passes the Claude token in the launch's `ax ssh` argv only (plan Q20). |
| [`ax-exec`](./ax-exec) | The AX stack's `cdr-exec`: run one command in an existing task (`just exe-ax-exec`), resuming it if Suspended and suspending it again afterwards. Never deletes a task. |
| [`ax-lib.sh`](./ax-lib.sh) | What `ax-job` and `ax-exec` share: the lease check, waiting for Running, the detached run and its polls, output redaction, and reading the Claude token. |
| [`ax-job-guest.sh`](./ax-job-guest.sh) | The half that runs inside the task, sent through `ax ssh` one short call at a time: launch the command once, detached in its own session under `/tmp/ax-job/`; poll its output and exit code; kill its process group. Never one long stream, since a silent `ax ssh` resets (Phase 5). POSIX sh, for the image's dash. |

All scripts must be idempotent (per `scripts-guidelines` in CLAUDE.md).

## Related docs

- [`../docs/usage.md`](../docs/usage.md) — user-facing quick reference
- [`../docs/runbook.md`](../docs/runbook.md) — day-to-day operator
  workflow (uses `cdr` for every Coder API call)
- [`../docs/architecture.md`](../docs/architecture.md) — full
  exe.hironow.dev architecture
- [`../coder/templates/dotfiles-devcontainer/README.md`](../coder/templates/dotfiles-devcontainer/README.md)
  — workspace template; `cdr templates push` is the deployment path
- [`../../tests/unit/test_cdr_wrapper.py`](../../tests/unit/test_cdr_wrapper.py)
  — regression tests for `cdr` (secret refresh, cleanup-on-failure,
  empty-payload guard)
- [`../../tests/unit/test_exe_ax_wrappers.py`](../../tests/unit/test_exe_ax_wrappers.py)
  — `ax-job` / `ax-exec` against a fake AX whose `ax ssh` runs
  `ax-job-guest.sh` for real: exit codes, the lease checks, the image and
  its tag, the timeout's process-group kill, reset polls and lost replies,
  a drain mid-command, and where the Claude token may and may not appear
