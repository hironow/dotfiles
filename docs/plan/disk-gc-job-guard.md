# Plan: Stop `just disk-gc` while a job is running

## Why

At 2026-11-16 01:33 JST, the WSL leg of `just disk-gc` (`scripts/disk_gc.sh clean`) deleted `~/.cargo/registry/{src,cache}` while a Rust CI job was building on the WSL runner.
While rustc was compiling a registry crate (`darling`), it lost its cwd and panicked.
For registry crates, cargo 1.95 sets rustc's cwd to the crate's extracted source directory (`path_args` in `util/workspace.rs`).
The 13 `.d` errors that followed came from `try_canonicalize(pkg_root)` in `fingerprint/dep_info.rs` hitting ENOENT.
Evidence: `registry/src` and `registry/cache` have birth time 01:49 while `index` remains 7/17, lines 70-71 of `disk_gc.sh` target those exact two paths, and PowerShell history confirms the run.

`runner_gc.sh` checks for running jobs, whereas `disk_gc.sh` does not.
Yet the justfile still describes `just disk-gc` as "safe unattended".

Windows profile caches (`~/.cargo`, uv, bun) are also shared with jobs of the Windows-native runner (`actions-runner-win`, user absin), so the same failure can happen there.

## What to change

Add a guard to `clean` in `scripts/disk_gc.sh`, and add one check line to `report`.

1. Add a function `_runner_job_state` returning a 3-state status for that leg's runner jobs (0 = running, 1 = idle, 2 = unknown):
   - Linux / WSL: `pgrep -x Runner.Worker` (same as `runner_gc.sh`; `-f` would match itself). rc 0 → running, 1 → idle, anything else (e.g., 127) → unknown.
   - Windows (Git Bash): `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' tasklist /FI "IMAGENAME eq Runner.Worker.exe" /FO CSV /NH`.
     Non-zero rc → unknown. If output contains `"Runner.Worker.exe"`, running; otherwise idle (the "no tasks" message varies by locale, while the image name appears verbatim).
   - Under `set -eu`, capture as `_st=0; _runner_job_state || _st=$?` (so idle rc=1 does not abort the script).
2. Check right before each deletion step (`mise prune`, `go clean -modcache`, `go clean -cache`, and each `rm -rf` in the cache loop).
   If running, print `SKIP: a runner job is executing (Runner.Worker alive); rerun when idle` and exit 0 without deleting anything further.
   If unknown, print `SKIP: cannot tell whether a runner job is executing; nothing more deleted` and exit 2 (fail-closed; the WSL leg prints "WSL leg failed" on the caller side).
   Replace the current `printf | awk | while` pipeline in the cache loop with a here-string so `exit` terminates the script instead of only a subshell.
3. Use `DISK_GC_ALLOW_BUSY=1` as the override key (matching `RUNNER_GC_ALLOW_BUSY` in runner-gc; deleting active caches fails running jobs).
   Do not mention the override in the SKIP line; document it in the runbook. Normalize the value to 0/1 and embed it in the `bash -lc` command line when invoking the WSL leg from Windows (`wsl.exe -e` does not inherit the caller's environment).
4. Check per leg: the WSL leg runs `disk_gc.sh` inside the distro and checks the WSL runner; the Windows leg checks the Windows runner. If one leg skips, the other continues.
5. Add one line `runner job: busy|idle|unknown` to `report`, giving a way to verify real detection on a physical machine without deleting anything.
6. Fix "safe unattended" in `justfile`'s `disk-gc` description and the header comment in `disk_gc.sh`.
   Document the guard behavior in `docs/runbook/runner-disk-gc.md` under the development caches section, and add this rule to the running-job detection section:
   "Any cleanup deleting paths shared with runner jobs must check job state immediately before each deletion step. 'Re-creatable' does not mean 'safe to delete while in use'."

## What we will not do

- Cannot prevent a job that starts between check and deletion (the check is an observation, not a lock, same limit as runner-gc). Checking right before each step minimizes that window; do not add locks or pre-deletion staging (`mv`).
- Keep the list of target caches unchanged. Keep ADRs unchanged (supplement with the runbook rule).

## Independent review (subagent, APPROVE WITH CHANGES)

Adopted all 6 findings; every one was verified on a physical machine or in code:

1. Fail-open: measured that running `tasklist` without MSYS conversion rewrites `/FI` to `C:/…/FI` and returns rc=1. Under `set -eu` without pipefail (`disk_gc.sh:22`), this was misjudged as "idle". → 3-state return, static check on the `tasklist` line, strict argv checks in fakes.
2. Checking only once: `runner_gc.sh:262` and `:302` re-check before each item. → Check right before each step.
3. Real detection unexercised anywhere. → Add check line to `report`.
4. Test isolation. → Build env from scratch, match `test_podman_gc_simulation.py` PATH, pre-verify fakes, parameterize both branches with fake `uname`.
5. `FORCE` naming conflicts with repo conventions. → Rename to `DISK_GC_ALLOW_BUSY` and normalize value.
6. Runbook. → Item 6 above.

## TDD

- **[Red]** Create `tests/unit/test_disk_gc_job_guard.py`, parameterizing Linux and Windows branches with a fake `uname`.
    - Create caches under fake HOME and LOCALAPPDATA; place fake `pgrep`, `tasklist`, `mise`, and `go`. Fake detectors exit 2 if argv does not match expectations.
    - Build env from scratch. Before running, verify fake bins are resolved and `wsl.exe`, `powershell.exe`, and `tasklist.exe` are unreachable.
      Also run `report` in the same env and verify every candidate path lies under tmp.
    - Five cases:
        - idle (control): caches deleted, `mise` and `go` called (prevents a silent bug where the guard always skips).
        - busy from the start: nothing deleted, prints `SKIP`, exits 0.
        - unknown (fake exits 3 / exits 1): nothing deleted, exits 2.
        - becomes busy midway (fake reports busy after the first cache is deleted): later caches remain.
        - `DISK_GC_ALLOW_BUSY=1`: deletes even while busy.
    - `report` outputs the `runner job:` line.
    - Static checks: logical line calling `tasklist` includes `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL`; WSL leg dispatch line includes `DISK_GC_ALLOW_BUSY`.
- **[Green]** Implement items 1-5 under "What to change".
- **[Refactor]** Item 6 (descriptions and runbook).

## How to verify

- `uv run pytest tests/unit/test_disk_gc_job_guard.py tests/unit/test_runner_gc.py` (native Windows; Linux branch also passes via fake `uname`).
- `just ci` lint (shellcheck, ruff, ty, markdownlint) and unit tests.
- Physical machine: `just disk-report` prints `runner job:` lines matching actual state for both legs (busy during a WSL job, idle when idle). Do not run `clean`.
