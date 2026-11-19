# Launch interactive-session scheduled tasks without a window (v4)

Date: 2026-11-18 (JST)

Owner request (2026-11-18): When running CI or checks on Windows, a terminal briefly appears. Inspect what is spawning it and fix it.
After reviewing the inspection results, the owner replied: "Yes, please proceed" (translated).
This plan covers fix #1 (scheduled tasks).

v1 wrapped tasks with `conhost.exe --headless`. Codex review ("Review record" below) revealed that exit codes are lost (so status never emits FAIL) and that there was no procedure to switch a running old keepalive.
v2 switched to a small Go launcher that returns the child's exit code.
v3, after the second review, stored the launcher under a content-hash directory, moved machine operations to an elevated terminal, and avoided relying on new code for rollback.
v4, after the third review, removed stopping old instances from the installer and made switching use the same temporary-client procedure as rollback to keep the distro alive. Launcher verification runs before removing any task.

## Facts (verified by inspection and experiments)

- `dotfiles-runner-watchdog` launches `powershell.exe` with an Interactive principal every 5 minutes and at logon (`scripts/runner_watchdog_win.ps1:102-113`).
    - Nothing hides the window.
    - `%TEMP%\runner-watchdog-win.log` on this machine has entries every 5 minutes (04:48, 04:53, 04:58, 05:03).
    - This is the primary cause of the brief terminal window the owner saw.
- `dotfiles-wsl-autostart` launches `powershell.exe` at logon and during install (`scripts/install_runner_gc_win.ps1:159-183`).
    - Because no principal is specified, it runs in the owner's session.
    - Its payload stays running indefinitely at the end as a WSL keepalive (`scripts/wsl_autostart.ps1:139-142`), leaving its window open.
    - Closing that window drops the keepalive and stops WSL in about 1 minute.
    - Payload logs go only to `Write-Host`, not to a file (`wsl_autostart.ps1:61-63`).
- `dotfiles-runner-gc` runs as S4U on this machine (works without logon), showing no window. When registered as Interactive after declining UAC (`install_runner_gc_win.ps1:126-131`), it flashes a window every hour. Status reads this task's `LastTaskResult` (`scripts/gc_status.sh:218-222`).
- Status reports FAIL when autostart's result is neither 0 nor 267009 (running) (`gc_status.sh:245-250`). A missing keepalive is only WARN (`gc_status.sh:183-188`). Thus, surfacing the payload's exit code as the task result is a prerequisite for FAIL detection.
- Experiments (2026-11-18, this machine, Windows 11 26300):
  1. `conhost.exe`, with or without `--headless`, never returns the child's exit code (returns 0 even when the child exits 7). When launched from Task Scheduler, the task result was also 0. → Dropped the conhost approach.
  2. A child launched from a windowless parent has a console without a window. `powershell.exe` launched from this shell has `GetConsoleWindow()` = 0 and runs `wsl.exe` normally. Launching a child with Windows `CREATE_NO_WINDOW` (0x08000000) produces this state (Microsoft describes it as a "console process without a console window"). Another of the owner's repos also spawns workers with this flag.
- Deleting a scheduled task registration does not stop a running task instance (Microsoft `schtasks /delete` documentation). The current installer re-registers autostart without stopping running old instances. Because the new payload exits with "nothing to do" if a keepalive already exists (`wsl_autostart.ps1:91`), the old window stays open and the switch never completes.
- Task Scheduler kills the task's process tree when stopping a task or hitting its time limit (installer assumption, comment in `install_runner_gc_win.ps1:164-166`). Verify during machine operations that no old keepalive remains after switching.
- All dotfiles Windows CI jobs run on GitHub `windows-latest`, not on this machine's desktop. New Go modules are tested automatically by the `windows-go` job (`just go-test go`, which discovers `tools/**/go.mod`).

## Design

- **`tools/run-hidden`** (Go, stdlib only): `run-hidden.exe <program> [args...]`.
    - Build with the Windows GUI subsystem (`-ldflags=-H=windowsgui`). Having no console of its own, it spawns no window when started by Task Scheduler.
    - Spawn the child with `CREATE_NO_WINDOW`, wait for it to finish, and return the child's exit code as its own exit code (so it appears in the Task Scheduler result).
    - Connect the child's stdin/stdout/stderr to `NUL` (nobody reads task windows today anyway).
    - Exit 2 when no arguments are passed; exit 1 when spawning the child fails (both appear in task results).
    - Outside Windows, do nothing and refuse with exit 2 (nowhere to use it).
    - Named `hidden` to match Windows terminology (`SW_HIDE`, `-WindowStyle Hidden`).
- **Build and placement**:
    - Recipe `run-hidden-build` builds `output/run-hidden/run-hidden.exe` (same as other tools: `CGO_ENABLED=0 GOTOOLCHAIN=local mise exec -- go build -trimpath`). Does nothing outside Windows.
    - The installer copies it to `%LOCALAPPDATA%\dotfiles\run-hidden\<first 16 hex chars of SHA-256>\run-hidden.exe`, and tasks invoke that copy.
        - Independent of working-tree branches (same reason as the watchdog copy, ADR 0042).
        - Content-addressed directory avoids overwriting a running exe (the autostart launcher keeps running while waiting on the keepalive). If the binary matches, reuse the existing path without copying; if it changed, copy to a new directory and point task actions there. Leave old directories untouched (owner cleans up).
        - Copy to a temporary name first, verify the hash, then rename. Abort installation if any existing copy has a hash mismatch against its directory name.
    - Put the copy logic in one function in `scripts/run_hidden_win.ps1` and dot-source it from both installers.
    - If the source binary is missing, abort installation and instruct to run `just run-hidden-build`.
- **Actions for the 3 tasks**: set actions on `dotfiles-runner-watchdog`, `dotfiles-wsl-autostart`, and `dotfiles-runner-gc` to `-Execute <run-hidden copy> -Argument '"<powershell.exe>" <same args as now>'`. Keep payload, arguments, triggers, principals, and settings unchanged. Wrap GC too: S4U already shows no window, and this removes the window even for Interactive registrations when UAC is declined while preserving exit codes in task results.
- **Switching autostart**: do not add instance-stopping logic to the installer.
    - If registration or startup fails after stopping the old instance, the distro loses its last client and shuts down, killing running runner jobs. Rollback inside the installer is heavy.
    - After switching to run-hidden, leaving an old instance running shows no window and causes no harm (the new payload sees the keepalive and exits, same as today).
    - To switch immediately (for this migration and future launcher version updates), follow "Machine operations" below to hold the distro with a temporary client before stopping. Rollback uses the same procedure. Document this in the runbook.
- **Verification order**: installers copy and hash-verify the launcher and check payload existence before deleting any task. The current GC installer deletes tasks first (`install_runner_gc_win.ps1:51-61`), leaving tasks deleted if copying fails.
- **Autostart log**: `wsl_autostart.ps1`'s `Write-Log` writes to `%TEMP%\wsl-autostart.log` in addition to `Write-Host`. Like watchdog's `Write-WdLog`, truncate to the last 200 lines when exceeding 1 MB.
- **Status**: if any of the 3 tasks does not invoke `run-hidden.exe`, emit WARN ("opens a console window on each run; elevate and re-install"). Cap at WARN since it requires manual action (ADR 0066). Leave FAIL rules unchanged (exit codes still reach task results).
- **ADR**: propose a new ADR stating "Windows scheduled tasks registered by dotfiles run through run-hidden". Rejected alternatives and reasons:
    - `-WindowStyle Hidden`: creates the console first and hides it afterwards, so it flashes briefly.
    - `conhost --headless`: drops the exit code.
    - All S4U: requires elevation to register; unverified whether `wsl.exe` keepalive works from an S4U session.
    - VBScript: deprecated by Windows.
    - Add a row to `docs/decision-queue.md`. Owner decides.

## Workflow (TDD)

1. **Red** (confirm failures before moving to Green):
   - Go (`tools/run-hidden`, windows build tag):
     - Launching `cmd.exe /c exit 7` returns 7.
     - Child (spawning the test binary itself as a helper) has `GetConsoleWindow()` == 0 or `IsWindowVisible` == false.
     - No arguments exits 2.
     - Missing program exits 1.
     - Outside Windows exits 2.
   - `tests/unit/test_run_hidden_install.py` (runs the function in `scripts/run_hidden_win.ps1` via pwsh, with root = `tmp_path`):
     - Copies to `<root>\<hash16>\run-hidden.exe` and returns that path.
     - Calling again with identical contents returns the same path without recopying (mtime unchanged).
     - Different contents copy to a new directory while leaving the old directory intact.
     - Missing source aborts with an error mentioning `just run-hidden-build`.
     - Existing copy whose hash mismatches its directory name aborts.
   - `tests/unit/test_runner_mode_win.py`:
     - Watchdog action executes the path returned by that function, and `-Argument` starts with the powershell path followed by the existing arguments (installed copy's `-File`).
   - `tests/unit/test_wsl_autostart.py`:
     - Autostart and GC actions have the same shape.
     - In both installers, the call to copy the launcher precedes the first `Unregister-ScheduledTask`.
     - Installers do not call `Stop-ScheduledTask` (switching is manual via runbook steps).
     - In pwsh payload tests, point `TEMP` to `tmp_path` and verify `Write-Log` writes lines to `%TEMP%\wsl-autostart.log`. Also point `TEMP` and `TMP` to `tmp_path` in existing `_run_payload` so it never writes to real `%TEMP%`.
   - `tests/unit/`:
     - Recipe `run-hidden-build` builds with `-H=windowsgui`.
     - `runner-watchdog-install`, `runner-mode-interactive`, and `runner-gc-install` invoke it first.
     - Status inspects the 3 tasks' actions and emits WARN when missing.
2. **Green**: implement per the design above.
3. **Documentation**:
   - Add a "Scheduled tasks running in interactive sessions" section to `docs/runbook/windows-host.md` (why run-hidden, rejected options, elevation needed to re-register).
   - Add the log path to the autostart row in `docs/runbook/runner-disk-gc.md`.
   - ADR and decision queue.
4. Verification:
   - `just ci` and `just check` (this machine).
   - PR CI (`windows-go` runs run-hidden's Go tests on Windows).
5. Machine operations (post-merge; requires owner approval; perform both in an **elevated terminal opened by the owner**):
   - All 3 tasks on this machine were registered elevated. An unelevated installer cannot delete them, leaves them unchanged, and skips the GC UAC path (`install_runner_gc_win.ps1:51-61,84`), so unelevated runs will not switch them.
   1. watchdog: run `just runner-watchdog-install` in an elevated terminal (do not restart the runner listener). Because watchdog finishes in seconds, no stop step is needed.
   2. autostart and GC (switch procedure; same pattern as rollback):
      1. In another terminal, start a temporary client to keep the distro alive: `wsl.exe -d Ubuntu-26.04 -e sleep 900`.
      2. If autostart is Running, run `Stop-ScheduledTask dotfiles-wsl-autostart`. Verify with `Get-CimInstance Win32_Process` that no old powershell or `wsl.exe` containing `dotfiles-wsl-keepalive` remains (the temporary client has a different command line and is distinguishable).
      3. Run `just runner-gc-install` in the elevated terminal. After registration, the installer starts autostart and connects the new keepalive.
      4. On failure, keep the temporary client running, fix the cause and retry step 3, or roll back using "On failure" below. The temporary client exits after 15 minutes; restart it if operations take longer.
   3. Verify:
      - `Get-ScheduledTask dotfiles-runner-watchdog, dotfiles-wsl-autostart, dotfiles-runner-gc | % Actions` points to `run-hidden.exe`.
      - The `wsl.exe` keepalive (command line containing `dotfiles-wsl-keepalive`) has powershell as its parent and `run-hidden.exe` as its grandparent, with no old keepalive left (`Get-CimInstance Win32_Process`).
      - Watchdog log continues receiving entries every 5 minutes.
      - `just status` is OK with no new WARN.
      - Owner observes for ~10 minutes and sees no windows.
      - On next logon, autostart launches from run-hidden and connects the keepalive (`just status`).
   4. Once verified, terminate the temporary client.

## Out of scope (found during inspection, handled separately)

- Adding `CREATE_NO_WINDOW` to spawning in rtk hooks and test helpers (fix #2).
- Store `python3` stub in `rtk-hook-claude.sh` (fix #3).
- Agent definitions disappearing on `j-cc` resume (fix #4).
- The main runner window (`dotfiles-runner-interactive`, `run.cmd`) stays visible by design; CI job children inherit that console. Leave unchanged.

## On failure

Rollback must not depend on stop logic in the new installer (reverting removes that logic too). With owner approval, run the following steps in order in an elevated terminal:

1. Revert the PR and pull main.
2. Hold the distro with a temporary client: start `wsl.exe -d Ubuntu-26.04 -e sleep 900` in another terminal.
3. Run `Stop-ScheduledTask dotfiles-wsl-autostart`. Verify with `Get-CimInstance Win32_Process` that no child powershell of `run-hidden.exe` and no `wsl.exe` with `dotfiles-wsl-keepalive` remains.
4. Run `just runner-watchdog-install` and `just runner-gc-install` (restores original actions launching `powershell.exe` directly).
5. Verify in `just status` that keepalive is OK and the autostart task is Running.
6. Terminate the temporary client from step 2.

Remove `%LOCALAPPDATA%\dotfiles\run-hidden\` and probe task `dotfiles-headless-probe` during owner cleanup only after confirming no task uses them (owner instruction, 2026-11-18).

## Review record

### Codex round 1 (v1, 2026-11-18)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | No procedure to switch an already-running old keepalive (P1) | Adopted | Installer only re-registers without stopping (`install_runner_gc_win.ps1:147-183`). New payload exits if a keepalive exists (`wsl_autostart.ps1:91`). Stop if Running before re-registering, and added parent-child checks to machine operations |
| 2 | Exit codes are lost and FAIL stops firing (P1) | Adopted (changed approach) | Confirmed by experiment that conhost drops exit codes. Status emits FAIL based on autostart result (`gc_status.sh:245-250`). Instead of inventing an alternate status check, switched to a launcher that returns exit codes so existing FAIL logic stays intact |

### Codex round 2 (v2, 2026-11-18)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | Written steps trigger no UAC on this machine and fail to switch (P1) | Adopted | Failing to delete existing S4U tasks unelevated sets `keepGcTask`, and UAC sits inside `if (-not $keepGcTask)` (`install_runner_gc_win.ps1:51-61,84`). Changed machine operations to run in an elevated terminal opened by the owner |
| 2 | Cannot overwrite a shared `run-hidden.exe` while it is running (P1) | Adopted | Autostart's launcher stays running waiting on the keepalive, keeping its exe locked. Switched to content-hashed directories and skip copying when identical; pin this behavior in pwsh tests |
| 3 | Reverting also removes stop logic, breaking rollback (P1) | Adopted | Post-revert installers only re-register. Switched to holding the distro with a temporary client, explicitly stopping and verifying before running the original installers |

### Codex round 3 (v3, 2026-11-18)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | Normal switching also needs a temporary client and failure recovery; pre-checks belong before stopping; test registration/startup failures with fake task ops (P1) | Adopted (adjusted form) | Stopping before a failed registration indeed shuts down the distro. Instead of adding stop+rollback code to installers, removed stop logic from installers and unified switching with rollback. Consequently, fake task-op tests are unneeded (installers do nothing after failure). Adopted pre-checks by moving launcher copy before the first `Unregister-ScheduledTask` (current GC installer deletes first, `install_runner_gc_win.ps1:51-61`) |

### Codex round 4 (v4, 2026-11-18)

APPROVE. No further findings.
