# 0042. Watchdog for the interactive Windows runner

**Date:** 2026-09-03
**Status:** Accepted

## Context

The gpu-win runner runs INTERACTIVELY (`just runner-mode-interactive`): a
logon scheduled task starts `run.cmd` in the user's session because GUI e2e
and CodeQL need that session, not Session 0. That mode has no supervisor.
`run.cmd` re-launches the listener only on the runner's own "retryable" /
"updating" exit codes and exits 0 on "terminated"; the logon task has no
restart policy and fires only at logon.

Third live report (2026-09-03, h-nn): the listener vanished at 16:24:16Z
right after a cancelled job - `_diag` ends mid-retry with no shutdown line,
the Application log has no crash, and Task Scheduler history was disabled,
so the death has no recorded cause. The box stayed OFFLINE for 34 minutes
while jobs queued behind it, until a human started the task by hand. Earlier
(2026-08-30) a second start path - a Startup-folder shortcut left by the
pre-repo script - raced the logon task and the loser looped on "A session
for this runner already exists".

## Decision

1. **A watchdog task** (`dotfiles-runner-watchdog`, `scripts/runner_watchdog_win.ps1`):
   at logon and every 5 minutes, if no `Runner.Listener` is alive, re-fire
   `dotfiles-runner-interactive`. That is its only action - it never kills
   (a killing watchdog is a second way to lose an in-flight job). Every run
   appends one dated line to `%TEMP%\runner-watchdog-win.log`; a restart is
   loud there even when Windows itself recorded nothing.
2. **One start path.** The mode switch and the watchdog installer remove any
   Startup shortcut that points at the runner's `run.cmd`.
3. **Task Scheduler history ON** (`wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true`),
   done by the elevated mode switch, so the next task death carries a cause.
4. Installed by `just runner-mode-interactive` (the one place the interactive
   stack is assembled) and re-installable alone with `just runner-watchdog-install`.
   `just runner-mode-service` removes it, else it would resurrect the
   interactive listener next to the service.

## Consequences

- Recovery from a silent listener death is bounded by the interval (5 min)
  instead of "next logon". Unattended REBOOT recovery is unchanged: it still
  needs auto-logon for the runner user (a human decision, deliberately not
  automated here).
- The watchdog cannot tell WHY the listener died; it only bounds the damage
  and dates it. The cause of the 2026-09-03 death stays open until history
  and the watchdog log catch the next one.
- Static tests: `tests/unit/test_runner_mode_win.py` (watchdog exists,
  generic, never kills, wired into both mode directions, legacy .lnk removed,
  history enabled).
