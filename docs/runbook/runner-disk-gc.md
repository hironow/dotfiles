# Self-hosted runner disk GC

This runbook covers disk reclamation for machines hosting self-hosted runners (native Windows and WSL) and pitfalls to avoid when modifying it (ADR 0035).
Read it before changing `scripts/runner_gc*`, `just runner-gc*`, `just status`, `just disk-gc`, or `just wsl-compact`.

## Why reclamation is needed

Container images, stopped containers, and build caches accumulate in the runner's WSL `ext4.vhdx`. Managed runtimes are limited to Podman 5 and newer (ADR 0067); existing Docker inventory is left untouched.
Left unchecked, C: fills up; with no free space, the vhdx cannot expand and WSL itself fails to boot (`I/O error @util.cpp` followed by systemd startup failure).
You cannot recover from that state on your own because WSL will not start to free space.

`just runner-gc-install` configures GC with `RUNNER_GC_RETENTION` (default 2 hours). Containers and images are judged by creation time, and workspaces by the usage stamp described below. Build and mount caches are not automatically reclaimed; the earlier cache-growth cap guarantee is not carried forward, so disk space monitoring remains necessary:

- **job-completed hook**: after every job
- **hourly timer**: every hour (runs as root)
- **journald cap**: bounds log growth (`RUNNER_GC_JOURNAL_MAX`, default `200M`)
- **`dotfiles-wsl-autostart`** (Windows logon task): restarts the distro's systemd (runner and GC timers) after reboot; logs to `%TEMP%\wsl-autostart.log`

The two Windows tasks launch through `run-hidden.exe` so no window appears on the owner's desktop (see "Scheduled tasks running in interactive sessions" in [Windows hosts](windows-host.md), ADR 0081).

Check status with `just status`.
It displays timers, tasks, and hooks for both Windows and WSL, and checks that the hook format is accepted by the runner and was not rejected on the most recent job.

## Hook registration

The runner validates hook paths and rejects anything without a `.sh`, `.ps1`, or `.js` extension with `ArgumentException: ... is not a valid path to a script`.
The value must be a path; command lines such as `powershell.exe -File <script>` fail the same check.
Rejections appear only in the job's own Worker log—not in journal or task history—so rely on `just status` to confirm acceptance.

## Detecting running jobs

Job detection uses `pgrep -x Runner.Worker`.
`pgrep -f` matches GC's own command line, causing it to think a job is always running and silently skip GC forever.

Because the hook is invoked from inside `Runner.Worker`, naive detection would always skip due to the job that launched it.
It checks process ancestors and backs off only when a non-ancestor worker (another concurrent job) exists.

Every step deleting paths shared with runner jobs checks for running jobs right before deleting.
"Can be regenerated" does not mean "safe to delete while in use".
Because cargo compiles registry crates with rustc using their extracted directory as cwd, deleting `~/.cargo/registry/src` breaks an in-flight rustc build.
If detection cannot tell, it treats a job as running so a broken check never silently starts deleting.

## Podman reclamation

GC checks both the Podman CLI and target runtime separately and requires both to be version 5 or newer. Unix also requires `jq`. If unavailable or version/info is unknown, it keeps Podman inventory and logs a diagnostic. It never falls back to Docker, guesses sockets, or initializes, starts, or updates machines. `version.Version` in `podman info --format json` is the target runtime version, not the CLI version. Local execution (`host.serviceIsRemote=false`) is also valid.

Rootful and rootless inventories differ by owner. The root timer runs root reclamation and then re-runs reclamation as the runner directory owner (`runuser`, `HOME`, `XDG_RUNTIME_DIR`). It clears inherited `CONTAINER_HOST` and `CONTAINER_CONNECTION` so that user's connection config applies. The rootless pass covers only Podman and does not repeat workspace or apt cleanup.

### Deletion criteria

Retention accepts a non-negative decimal integer with `s`, `m`, `h`, or `d` (default seconds). Leading zeros are not treated as octal, so `08h` is valid. Explicit `0` still specifies zero retention. If clock lookup fails, is invalid, is outside signed Unix integer range, or retention would reach before the Unix epoch, both containers and images are kept and a diagnostic is printed. If Unix prints `invalid or excessive retention`, `invalid clock`, `clock query failed`, or `clock outside signed range`, check config and system clock. Bounds are checked before multiplication so overflow never shortens retention. This validation applies to the Podman phase; existing policies for workspaces and other targets remain unchanged.

Image IDs accept only a full 64-character lowercase hex string or the same prefixed with `sha256:`. Listing results, image inspections, and container image references are normalized to that form for comparison. Short IDs and unknown formats are never used for deletion. Container IDs are matched separately.

- Containers and images are listed separately. If listing fails, that cleanup phase aborts. If container reference info is incomplete, images are kept.
- Only stopped containers created earlier than the retention window are removed without force via `podman rm <ID>`. If a container starts after the check, the runtime refuses removal. Volumes are never deleted.
- Images are checked for creation time, all `RepoTags`, and container references. Images whose info fails to fetch or parse are kept. Image info is re-read right before deletion.
- Creation time `Created` is read as the raw string written by Podman; non-string values are kept as unknown age. Windows GC runs on Windows PowerShell 5.1, which leaves JSON dates as strings; PowerShell 7.5+ also reads them as strings via `ConvertFrom-Json -DateKind String` (7.0-7.4 are unsupported). If a `Created` value parses as a `DateTime`, that item is kept (failing safe); unparseable formats such as nanosecond timestamps pass normal inspection as strings.
- If any alias matches `RUNNER_GC_KEEP_TAG_PREFIX` (default `keep/`), the entire image is kept. `keep/model:latest` and `localhost/keep/model:latest` match the same protection; arbitrary prefixes and registry-qualified names work.
- Deletion uses only individual `podman rmi --no-prune <ID>` calls—no forced removal and no cascading parent-image removal. Images rejected due to new container references or multiple tags are left alone.

Add protection tags with `podman tag <image> keep/<name>`. There is no atomic guarantee against a third party re-tagging after the final check. Non-forced removal rejecting new container references is a separate guarantee from tag races. Job detection is also a point-in-time observation, not a lock across all processes.

`system`, `builder`, and `buildx` prunes, bulk image prunes, and mount-cache cleanups are never called. In tested Podman 6.1.4, `image prune --all` or `--build-cache` deletes persistent caches regardless of image age, so they do not substitute for safe age-bounded reclamation.

### Scoped runs and verification

On Unix, `RUNNER_GC_PODMAN_ONLY=1` runs only the Podman phase, and `RUNNER_GC_DRY_RUN=1` enables that limit and prints candidates without deleting (it is not a dry-run for other janitors). Windows uses `-PodmanOnly`, `-SkipPodman`, `-DryRun`, and `-PodmanTimeoutSec` (default 300s). Every CLI call has a watchdog that terminates the process tree on timeout.

Legacy names `RUNNER_GC_DOCKER_ONLY=1`, `-SkipDocker`, and `-DockerTimeoutSec` remain as compatible options that do not widen deletion scope; they do not select Docker. If either the old or new `ONLY` variable is `1`, the Podman-only limit stays active.

For the model, implementation mapping, and seed replay with fake I/O, see [Podman GC verification scope](../plan/podman-gc.md). Tests never connect to real engines or inventories.

## toolcache reclamation

Workflows pin series like `go-version: 1.25.x`, `node-version: 22.x`, and `python-version: 3.13`, and `setup-*` uses the latest patch in each series.
So keeping the newest N versions overall would delete patches needed by a matrix (one runner may keep three active Python series).
GC keeps the latest patch per `major.minor` series and caps the number of series with `RUNNER_GC_TOOLCACHE_KEEP` (default 5).

- Sort with `sort -V`; lexicographic sorting puts `1.25.8` after `1.25.11` and deletes the newest version.
- Delete whole `<version>/` directories. Because `<version>/<arch>.complete` sits inside, partial deletion leaves a "cached yet missing its files" state.
- Because last-used time is unavailable, judge by series rather than timestamp (under `relatime`, traversing `_tool` updates atime and mtime is only install time).
- This step never runs while a job is executing, even with `RUNNER_GC_FORCE=1` (deleting an active toolcache breaks the job immediately).

## workspace reclamation

`_work/<repo>` checkouts grow larger than toolcache on both Windows and WSL, so both reclaim them.
Age is judged by the `.runner-gc-last-used` stamp updated by GC itself.
Directory mtime is not used because it misses nested rebuilds (Linux tracks only direct children, and Windows does not update parent `LastWriteTime` on nested file writes).

- Runner-owned directories are excluded by explicit name list (matching a leading `_` would permanently keep a real repo named `_foo`).
- Checkouts pointed to by `RUNNER_WORKSPACE` and `GITHUB_WORKSPACE` are always kept (so a hook running between steps never deletes the active job's checkout).
- `RUNNER_GC_ROOT` targets a single install (so destructive paths can be tested against a synthetic root since busy runners rarely sit idle).
- Running while a job executes requires both `RUNNER_GC_ROOT` and `RUNNER_GC_ALLOW_BUSY=1` (`RUNNER_GC_FORCE` does not substitute). Setting root only declares which install to target, not that it is safe to touch: manual runs lack `RUNNER_WORKSPACE` and cannot tell which checkout a running job is writing to.

On native Windows, plain `Remove-Item` is not enough.
There are junctions (PowerShell 5.1's `-Recurse` follows links and deletes targets), read-only `.git/objects`, and paths exceeding MAX_PATH (`node_modules`).
It removes reparse points non-recursively first, clears read-only attributes, and removes the rest with `robocopy /MIR /XJ`.

## Runner self-update leftovers

`_work/_update` and old `bin.*` and `externals.*` directories are reclaimed on a separate 24-hour window (2 hours would catch an active self-update).
Old versions are deleted only when `bin` and `externals` resolve as symlinks.
In standard installs, `bin.*` is the runner itself and deleting it breaks the runner.

## Reclaiming vhdx space back to C

Deleting files inside WSL does not increase free space on C:.
Because the vhdx still holds freed ext4 blocks on Windows, `fstrim` is what returns them.
If the vhdx is sparse, punching holes with `fstrim /` reclaims space online without administrator privileges.
GC runs `fstrim` at the end of root reclamation.

A vhdx is not always sparse. Moving it to another volume with `wsl --manage --move` can clear the sparse attribute (observed on 2026-11-17 when moving to D:).
On a non-sparse vhdx, `fstrim` returns nothing to the volume (example in memory `project_this_host_vhdx_non_sparse`).
Reclaiming space then requires administrator privileges and `wsl --shutdown` (stopping the runner), so `just wsl-compact` only measures and prints instructions.
It omits diskpart steps for sparse vhdx files; diskpart and Optimize-VHD reject sparse vhdx files with "must not be sparse".
`wsl --manage <distro> --compact` listed in `wsl --help` on this host's WSL (3.0.5) has not been verified here.
We do not enable `wsl --manage --set-sparse` automatically (ADR 0035). On WSL 3.0.5 it does not require `--allow-unsafe` and only warns that it is experimental.
Running `fstrim` on an already-sparse vhdx is separate and safe.

Slack space is measured using actual allocation (`du -B1`).
`stat -c %s` gives logical size (the high-water mark, which never shrinks), so "logical size - used space" double-counts space already returned.
`just wsl-compact` also shows sparse status.
It checks the file attribute directly (`fsutil sparse queryflag` text varies by locale, and even English "This file is NOT set as sparse" contains "sparse").

`just wsl-compact` also checks who can open the vhdx. The vhdx holds the whole distro, including runner credentials.
Only the current user, SYSTEM, Administrators, and WSL's own SIDs (`S-1-5-83-*`, `S-1-15-*`) are allowed.
Anything else triggers a WARN. `--move` inherits the destination volume's ACL, pulling in D:\ defaults such as `Authenticated Users:(M)`.
Fix the vhdx parent folder rather than the file (`icacls <folder> /inheritance:r /grant:r ...`; fixing only the file reverts on the next vhdx created).
After `wsl --manage --move`, check sparse status and ACLs with `just wsl-compact`.

PowerShell's `Get-Acl` fails to load when called from Git Bash because it inherits pwsh 7's `PSModulePath`.
When reading ACLs from a shell script, use .NET (`[IO.File]::GetAccessControl`) and reset `PSModulePath` to `$PSHOME\Modules`.

## Development caches

Besides containers, development caches grow large (`~/.cache/uv` alone reaches tens of GB).
`just disk-gc` also cleans the WSL runner user's HOME (skip with `DISK_GC_NO_WSL=1`).
Because this area is shared with interactive work, it is not on the hourly timer.

These caches are also used by runner jobs on the same leg.
So `clean` checks each leg for running jobs right before every deletion stage (`mise prune`, `go clean`, and each individual cache removal):

- The WSL leg checks `pgrep -x Runner.Worker` inside the distro; the Windows leg checks `tasklist /FI "IMAGENAME eq Runner.Worker.exe" /FO CSV /NH` (with Git Bash path conversion disabled).
- If a job is running, it prints `SKIP: a runner job is executing` and exits 0 without deleting the rest.
- If detection fails, it prints `SKIP: cannot tell` and exits 2.
- One leg stopping does not stop the other leg.
- `just disk-report` displays `runner job: busy|idle|unknown` for each leg, letting you verify live detection without deleting anything.
- Detection is a point-in-time check, not a lock; it cannot prevent a job starting between detection and deletion.
- To force deletion despite a running job, set `DISK_GC_ALLOW_BUSY=1` (also passed to the WSL leg). Any job using the deleted cache will fail.
`~/.cache/huggingface` is excluded by default (include with `DISK_GC_HUGGINGFACE=1`; a single model is tens of GB and much heavier to re-download than wheels).

## Passing commands from Windows to WSL

When invoking WSL GC from Windows, set `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL='*'` (target distro is `RUNNER_GC_WSL_DISTRO`, default `Ubuntu`).
Without them, Git Bash rewrites `/usr/local/bin/...`, `/mnt/c/...`, and even bare `/` into Windows paths before passing them to `wsl.exe`.
