# exe/scripts/

Operational scripts for `exe.hironow.dev`.

For a user-facing **how / when to pick which `cdr` command** quick
reference, see [`../docs/usage.md`](../docs/usage.md). This README
documents the file-level layout.

## Files

| Path | Purpose |
|---|---|
| [`cdr`](./cdr) | Wrapper around the upstream `coder` CLI. Fetches Cloudflare Access service-token credentials from Secret Manager (cached for 5 min), exports `CODER_HEADER_COMMAND`, then exec's `coder` with the original arguments. Symlinked into `~/.local/bin` via `just exe-cdr-install`. |
| [`cdr-header`](./cdr-header) | Helper invoked by `cdr` via `CODER_HEADER_COMMAND` to emit the `CF-Access-*` headers Coder needs on every API call. |
| [`cdr-job`](./cdr-job) | Run a single command in a fresh ephemeral Coder workspace per [ADR 0008](../../docs/adr/0008-event-driven-workspace-runner.md) (status: Superseded by [0009](../../docs/adr/0009-retract-cron-trigger-from-adr-0008.md) partial — cron retracted, operator-pulled job runner retained). Pure isolation, ~6 min boot tax. Trap-handler `coder delete` on exit. |
| [`cdr-exec`](./cdr-exec) | Run a command in an EXISTING long-lived workspace (warm reuse, ~10-30s start). State is NOT isolated between calls. See ADR 0008 amendment for the trade-off. |
| [`ax-job`](./ax-job) | The AX stack's `cdr-job`: run one command in a fresh AX task, then delete the task (`just exe-ax-job`). Checks the lease (`exe-reaper may-start`) before anything exists and again right before the launch, tags the digest-pinned image `inuse-<sha12>-<unix>` before the task exists, and deletes the task only once the command's end is certain. `--claude` passes the Claude token in the launch's `ax ssh` argv only (plan Q20). |
| [`ax-exec`](./ax-exec) | The AX stack's `cdr-exec`: run one command in an existing task (`just exe-ax-exec`), resuming it if Suspended and suspending it again afterwards. Never deletes a task. |
| [`ax-lib.sh`](./ax-lib.sh) | What `ax-job` and `ax-exec` share: the lease check, waiting for Running, the detached run and its polls, output redaction, and reading the Claude token. |
| [`ax-job-guest.sh`](./ax-job-guest.sh) | The half that runs inside the task, sent through `ax ssh` one short call at a time: launch the command once, detached in its own session under `/tmp/ax-job/`; poll its output and exit code; kill its process group. Never one long stream, since a silent `ax ssh` resets (Phase 5). POSIX sh, for the image's dash. |
| [`bootstrap.sh`](./bootstrap.sh) | First-time provisioning helper (tofu apply + cloudflared tunnel login). Idempotent. |
| [`teardown.sh`](./teardown.sh) | Destroys the GCE workspace VM and Coder template, retains Cloudflare + Tailscale state for re-bootstrap. Idempotent. |
| [`smoke.sh`](./smoke.sh) | Post-deploy connectivity checks (Tailscale up, CF Access reachable, SSH reachable, Coder UI 200). Idempotent. |

All scripts must be idempotent (per `scripts-guidelines` in CLAUDE.md).

## Related docs

- [`../docs/usage.md`](../docs/usage.md) — `cdr` / `cdr-job` /
  `cdr-exec` / `cdr-header` user-facing quick reference
- [`../docs/runbook.md`](../docs/runbook.md) — day-to-day operator
  workflow (uses `cdr` for every Coder API call)
- [`../docs/architecture.md`](../docs/architecture.md) — full
  exe.hironow.dev architecture
- [`../coder/templates/dotfiles-devcontainer/README.md`](../coder/templates/dotfiles-devcontainer/README.md)
  — workspace template; `cdr templates push` is the deployment path
- [`../../tests/test_cdr_wrapper.py`](../../tests/test_cdr_wrapper.py)
  — regression tests for `cdr` (secret refresh, cleanup-on-failure,
  empty-payload guard)
- [`../../tests/unit/test_exe_ax_wrappers.py`](../../tests/unit/test_exe_ax_wrappers.py)
  — `ax-job` / `ax-exec` against a fake AX whose `ax ssh` runs
  `ax-job-guest.sh` for real: exit codes, the lease checks, the image and
  its tag, the timeout's process-group kill, reset polls and lost replies,
  a drain mid-command, and where the Claude token may and may not appear
