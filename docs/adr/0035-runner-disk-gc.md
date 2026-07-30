# 0035. Time-based disk GC for the self-hosted runners (2h retention)

**Date:** 2026-07-31
**Status:** Accepted

## Context

The Windows host ran out of C: space (12.9 GB free of 461 GB). It carries
**two** self-hosted runners — `actions.runner.m4k3-co.trade_linux_wsl` inside a
WSL distro, and a native Windows one at `~/actions-runner-win` — and neither
collected anything.

Measurement found a single dominant consumer: the WSL `ext4.vhdx` backing the
distro, at **227 GB**. (The Windows runner was comparatively tiny at ~0.06 GB
of `_work`, but had 44 unrotated `_diag` logs and no GC of any kind, so it is
the same leak at an earlier stage.)

Inside that distro, `docker system df` reported:

| type        | size    | reclaimable |
| ----------- | ------- | ----------- |
| Images      | 90.5 GB | 76.7 GB     |
| Build Cache | 72.8 GB | 43.4 GB     |
| Containers  | 9.2 GB  | 9.2 GB      |

≈129 GB of pure garbage. Neither `/etc/docker/daemon.json` nor
`/etc/buildkit/buildkitd.toml` existed, i.e. **no GC policy was configured at
all**. Every devcontainer job leaves a stopped container, an unreferenced image
and a BuildKit cache generation behind, and nothing ever collected them — a
one-way ratchet.

Two failure modes made this worse than a slow leak:

1. **The ratchet is invisible from Windows.** A vhdx grows to its high-water
   mark and never shrinks. Freeing 100 GB inside the distro changes the
   Windows-side file size by zero.
2. **It deadlocks.** At 12.9 GB free the vhdx could not expand, so WSL failed
   to start at all (`I/O error @util.cpp:1399 (UtilInitGroups)` — systemd could
   not come up). The runner was down and the usual fix (shell in, prune) was
   unavailable until host space was freed from outside.

## Decision

**Collect on a time budget, not a size budget: keep anything used within 2 h,
drop everything older.** Implemented as `scripts/runner_gc.sh` plus an
idempotent installer, wired to three independent brakes:

| brake                                  | WSL leg                        | Windows leg                       |
| -------------------------------------- | ------------------------------ | --------------------------------- |
| collect right after each job           | `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` | same env var, `.ps1` payload |
| hourly floor (idle drift, missed hooks) | `runner-gc.timer` (Persistent) | Scheduled Task `dotfiles-runner-gc` |
| uncapped logs                          | journald `SystemMaxUse=200M`   | `_diag` trimmed at 7 days         |

`just runner-gc` and `just runner-gc-install` drive **both** legs from the
Windows side, so there is one command to remember rather than two.

A time budget beats a size budget here because back-to-back CI jobs on the same
repo still hit warm cache, while anything from an older job — the actual leak —
ages out within the hour. Retention is `RUNNER_GC_RETENTION`, default `2h`.

The GC **skips itself while a job is executing** so an in-flight `docker build`
never loses cache underneath it; the hourly timer retries.

### Detecting a running job

Job detection MUST use `pgrep -x Runner.Worker` (exact executable *name*).
`pgrep -f Runner.Worker` also matches the GC script's own command line, so it
reports a running job 100% of the time and silently disables the entire
mechanism. This bit us during development and is the single easiest way to
regress this file.

On the Windows leg `Get-Process -Name Runner.Worker` is already an
exact-name match, so it has no equivalent hazard — but its scripts **must stay
ASCII-only**: `powershell.exe` (5.1) reads a BOM-less UTF-8 script as ANSI, so
emoji in log lines arrive mojibake under the Scheduled Task.

### Windows → WSL dispatch

`just runner-gc` / `runner-gc-install` run from the Windows side, where the
runner is not. Both scripts re-enter the distro via `wsl.exe -u root`. Git Bash
rewrites any argument that looks like a unix path (`/usr/local/bin/runner-gc`,
`/mnt/c/...`, even a bare `/`) into a Windows path before `wsl.exe` sees it, so
each dispatch sets `MSYS_NO_PATHCONV=1` / `MSYS2_ARG_CONV_EXCL='*'`.

## Consequences

- Growth stops at the source; the vhdx no longer ratchets upward.
- **Existing slack is not recovered automatically.** Compaction is the only way
  to return it to Windows, and it needs Administrator *and* a full
  `wsl --shutdown` (runner offline). `just wsl-compact` therefore only measures
  the slack and prints the `diskpart` steps — advisory, like `just wsl-conf`.
- Colder cache for jobs spaced more than 2 h apart, in exchange for a bounded
  disk. Raise `RUNNER_GC_RETENTION` if CI wall-clock matters more than space.
- Host-side profile caches (mise/bun/uv/cargo/npm) are handled separately by
  `just disk-gc`, which only ever removes regenerable caches.

### Rejected: sparse VHD

`wsl --manage <distro> --set-sparse true` would return freed blocks to Windows
automatically and was the first choice. Microsoft currently ships it **disabled
behind `--allow-unsafe`** over a data-corruption risk:

> スパース VHD のサポートは、データ破損の可能性があるため、現在無効になっています。

Not acceptable on a host running CI. Revisit if the flag is re-enabled by
default.
