# 0035. Time-based disk GC for the self-hosted runners (2h retention)

**Date:** 2026-07-31
**Status:** Accepted

## Context

The Windows host ran out of C: space (12.9 GB free of 461 GB). It carries
**two** self-hosted runners — `actions.runner.m4k3-co.trade_linux_wsl` inside a
WSL distro, and a native Windows one at `~/actions-runner-win` — and neither
collected anything.

Measurement found a single dominant consumer: the WSL `ext4.vhdx` backing the
distro, at **227 GB**. The native Windows runner is the same leak an order of
magnitude behind, at **6.1 GB** and climbing with no GC of any kind:

| path                                | size   |
| ----------------------------------- | ------ |
| `_work/<repo>` (3 repos)            | 4.9 GB |
| `_diag` (1098 unrotated logs)       | 0.4 GB |
| `_work/_update` + superseded `bin.*`/`externals.*` + installer `.zip` | 0.6 GB |
| `_work/_temp`                       | 12 KB  |

`manga-uri` alone accounts for 4.1 GB of that, 3.7 GB of it a Rust `target/`.
The scratch directory an incomplete sweep would reach for is five orders of
magnitude smaller than the workspaces that actually grow.

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
| uncapped logs                          | journald `SystemMaxUse=200M`, `_diag` trimmed at 7 days | `_diag` trimmed at 7 days |
| stacked toolcache generations           | `_work/_tool/<tool>/<version>/`, newest N kept | (native runner installs tools per job) |
| idle job workspaces                     | (docker holds the build state)  | `_work/<repo>` past the retention |
| superseded runner versions              | (self-update replaces in place) | `_work/_update`, stale `bin.*`/`externals.*`, installer `.zip` |

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

### Reaching the runner's own Docker daemon

The hourly timer runs as root, and **root's Docker context is not the
runner's**. Where the runner drives *rootless* Docker, root resolves to
`/var/run/docker.sock` — a different daemon, typically empty — so every prune
succeeds against nothing while the real hoard at `/run/user/<uid>/docker.sock`
keeps growing. `docker info` succeeds against that empty daemon too, so both
`system df` lines read ~0 B and the sweep exits 0 having reclaimed zero: the
same silent-stop class as the `pgrep -f` trap, but reached by a different road.

Measured on the WSL box that hosts `actions-runner-linux-wsl`: the rootless
daemon held 148 GB of images and 128 GB of build cache while the rootful daemon
it would otherwise have swept held **0 B**.

So when running as root, the docker leg is re-entered once per runner install
as that install's **owning user** (`runuser -u <owner> -- env
XDG_RUNTIME_DIR=/run/user/<uid> … RUNNER_GC_DOCKER_ONLY=1 "$0"`), whose context
points at the daemon its jobs actually dirty. Root's own leg is kept as well,
which is what a rootful-only host needs — so neither topology regresses and no
host-type branching is required.

Identity, not socket path, is the key: the authority on *which* daemon to reach
is the Docker context store, not a `/run/user/*/docker.sock` glob. Running as
the owner delegates that decision to Docker instead of re-deriving it, and it
keeps working for hosts whose context points somewhere else entirely.

### Toolcache generations

`actions/setup-*` stacks a fresh `_work/_tool/<tool>/<version>/` per release and
never removes the previous one. On the WSL box this had reached 7 generations of
Go, 4 of `uv`, 4 of CodeQL — the last at ~1.7 GB each, roughly 30 GB a year from
CodeQL alone.

**Reap by series, not by count.** Workflows pin a *series* — `go-version:
1.25.x`, `node-version: 22.x`, `python-version: 3.13` — and `setup-*` resolves
it to the newest patch within that series. A flat "keep the newest N versions"
therefore evicts versions the matrices still need: three repos on this runner
(`rvc-hfie` 3.10, `m4k3` 3.13, `just-ag` 3.14) pin three different Python
series between them, so keeping only the newest would re-download two of them on
every job. Keeping **the newest patch of each series** protects exactly what a
series pin resolves to, and still reaps the patches it superseded.
`RUNNER_GC_TOOLCACHE_KEEP` (default 5) bounds how many series survive, so the
cache cannot grow without limit either; raise it if the matrices pin more series
than that.

Measured on the box, this keeps every pinned version and reclaims only dead
patches:

| tool   | kept                             | reaped                              |
| ------ | -------------------------------- | ----------------------------------- |
| Python | 3.10.20, 3.13.13, 3.14.6         | — (all three are matrix-pinned)      |
| node   | 22.22.3, 24.18.0                 | —                                    |
| go     | 1.23.12, **1.25.11**, 1.26.5     | 1.25.0, 1.25.8, 1.26.2, 1.26.4       |
| uv     | 0.11.33, 0.12.0                  | 0.11.21, 0.11.32                     |

Last-use would be the natural axis — it is what the 2 h budget uses everywhere
else — but there is no usable signal. The filesystem mounts `relatime`, and any
sweep that walks `_tool` (this one included) rewrites every atime it reads; the
investigation that produced this ADR flattened all of them to a single
timestamp. `mtime` is the *install* time, not the use time: Python 3.10.20 was
installed seven weeks before this measurement and is still pinned.

Two traps, both silent:

- **Ordering must be `sort -V`.** Lexically `1.25.8` sorts *above* `1.25.11`, so
  a plain `sort` keeps the older tool and deletes the newest. Both versions were
  present on the box, so this would have fired immediately.
- **The unit of deletion must be the whole `<version>/` directory**, because the
  `<version>/<arch>.complete` marker the runner trusts to decide a tool is
  cached lives *inside* it. Removing anything narrower leaves the cache
  advertising a tool that is no longer on disk.

This leg re-checks for a live job **even under `RUNNER_GC_FORCE=1`**. Losing
build cache to a forced prune only costs time, but deleting a `<version>/` that
a running job already resolved fails its next step outright — so the two are not
equally forceable.

### Ageing a workspace

`_work/<repo>` is where the Windows leg actually grows, and it is the one thing
here whose collection is irreversible — so it is aged on a marker file
(`.runner-gc-last-used`) the GC stamps itself, never on the directory
timestamp. **Windows does not bump a directory's `LastWriteTime` when a nested
file changes**: `manga-uri` was rebuilt the day before this was written and
still reported a mtime seven weeks old. Ageing on that inverts the policy
outright — hot checkouts read cold and get deleted, cold ones look fresh and
survive. Whatever `RUNNER_WORKSPACE`/`GITHUB_WORKSPACE` point at is excluded on
top of that, so a hook firing between steps cannot take the running job's tree.

Deleting the tree needs more than `Remove-Item -Recurse`, and each gap is a
different kind of damage:

- **Junctions.** Windows PowerShell recurses *through* a reparse point and
  deletes the target's contents — data outside the runner root. Links are
  detached first, non-recursively, so only the link is spent.
- **Read-only files.** `.git/objects` is read-only by design; one of them
  aborts the delete midway and leaves a half-removed tree that still fills the
  disk.
- **MAX_PATH.** `node_modules` nests past the limit on its own, and
  `powershell.exe` (5.1) — which is what the hook runs — gives up there.
  `robocopy /MIR /XJ` mirrors an empty directory over the remains, speaking the
  long-path API natively; `/XJ` so it cannot cross a junction either.

The cost is a fresh clone and a cold build on the next job for that repo. That
is the trade the 2 h budget already makes elsewhere, and it is why the marker
exists: back-to-back jobs keep their cache, a repo nobody has touched since
this morning does not.

Self-update leftovers (`_work/_update`, superseded `bin.*`/`externals.*`,
installer archives) get a **24 h floor of their own** rather than the 2 h
retention: the runner stages an update and only then swings the `bin`/
`externals` links over, so a two-hour window could catch one mid-flight.
Versioned directories are pruned **only when `bin`/`externals` resolve as
symlinks** — a plain install keeps the live runner in `bin.*` itself, where
deleting the "old" one would brick it.

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
- Version-matrix workflows keep their toolchains: series-based retention leaves
  the newest patch of every pinned series in place. A matrix that pins **more
  than `RUNNER_GC_TOOLCACHE_KEEP` (5) distinct series** of one tool would still
  lose the oldest, which costs a re-download but never breaks a job — the leg
  refuses to delete while one is running.
- An **exact-patch pin** (`python-version: '3.13.13'`) is re-downloaded once a
  newer patch in the same series lands, since only the newest patch of a series
  is kept. Series pins — what `setup-*` documents and what every workflow here
  uses — are unaffected.

### Rejected: sparse VHD

`wsl --manage <distro> --set-sparse true` would return freed blocks to Windows
automatically and was the first choice. Microsoft currently ships it **disabled
behind `--allow-unsafe`** over a data-corruption risk:

> スパース VHD のサポートは、データ破損の可能性があるため、現在無効になっています。

Not acceptable on a host running CI. Revisit if the flag is re-enabled by
default.
