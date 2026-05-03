# exe/scripts/

Operational scripts for `exe.hironow.dev`.

## Files

| Path | Purpose |
|---|---|
| [`cdr`](./cdr) | Wrapper around the upstream `coder` CLI. Fetches Cloudflare Access service-token credentials from Secret Manager (cached for 5 min), exports `CODER_HEADER_COMMAND`, then exec's `coder` with the original arguments. Symlinked into `~/.local/bin` via `just exe-cdr-install`. |
| [`cdr-header`](./cdr-header) | Helper invoked by `cdr` via `CODER_HEADER_COMMAND` to emit the `CF-Access-*` headers Coder needs on every API call. |
| [`cdr-job`](./cdr-job) | Run a single command in a fresh ephemeral Coder workspace per [ADR 0008](../../docs/adr/0008-event-driven-workspace-runner.md). Pure isolation, ~6 min boot tax. Trap-handler `coder delete` on exit. |
| [`cdr-exec`](./cdr-exec) | Run a command in an EXISTING long-lived workspace (warm reuse, ~10-30s start). State is NOT isolated between calls. See ADR 0008 amendment for the trade-off. |
| [`bootstrap.sh`](./bootstrap.sh) | First-time provisioning helper (tofu apply + cloudflared tunnel login). Idempotent. |
| [`teardown.sh`](./teardown.sh) | Destroys the GCE workspace VM and Coder template, retains Cloudflare + Tailscale state for re-bootstrap. Idempotent. |
| [`smoke.sh`](./smoke.sh) | Post-deploy connectivity checks (Tailscale up, CF Access reachable, SSH reachable, Coder UI 200). Idempotent. |

All scripts must be idempotent (per `scripts-guidelines` in CLAUDE.md).

## Related docs

- [`../docs/runbook.md`](../docs/runbook.md) — day-to-day operator
  workflow (uses `cdr` for every Coder API call)
- [`../docs/architecture.md`](../docs/architecture.md) — full
  exe.hironow.dev architecture
- [`../coder/templates/dotfiles-devcontainer/README.md`](../coder/templates/dotfiles-devcontainer/README.md)
  — workspace template; `cdr templates push` is the deployment path
- [`../../tests/test_cdr_wrapper.py`](../../tests/test_cdr_wrapper.py)
  — regression tests for `cdr` (secret refresh, cleanup-on-failure,
  empty-payload guard)
