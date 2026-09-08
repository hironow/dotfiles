"""Switch the native Windows runner between SERVICE and INTERACTIVE mode.

Why this exists (2026-08-21, second live report): the gpu-win runner was
re-enabled as a LocalSystem service (#312) — but that box runs GUI e2e
(manga-uri: WebView2 windows) and CodeQL jobs that need the user's profile.
Under Session 0 the jobs fail in three measured ways: CodeQL resolved its
config under C:\\WINDOWS\\system32\\config\\systemprofile, autobuild died on
UnauthorizedAccess with git missing from the (Machine) PATH, and WebView2
could not create a window at all. The service had been DELIBERATELY disabled
for exactly this reason by an ad-hoc, host-hardcoded script inside the
runner directory — unversioned, so the next tool (us) re-enabled the service
in good faith and reintroduced the failure.

The fix is a repo-managed, generic mode switch:

- `just runner-mode-interactive`: stop + Disable the service, register a
  logon scheduled task that runs run.cmd in the user's INTERACTIVE session
  (GUI-capable, user profile, user PATH), start it now, and prove the
  listener lives outside Session 0.
- `just runner-mode-service`: the inverse — unregister the task, re-enable
  (delayed-auto) and start the service — for boxes that only run headless
  jobs and need unattended reboot survival.

Static text assertions, matching tests/unit/test_runner_gc.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MODE = SCRIPTS / "runner_mode_win.ps1"
STATUS = SCRIPTS / "gc_status.sh"
JUSTFILE = ROOT / "justfile"


def _text() -> str:
    return MODE.read_text(encoding="utf-8")


def test_mode_switch_exists_and_is_generic() -> None:
    assert MODE.is_file(), "scripts/runner_mode_win.ps1 is missing"
    text = _text()
    assert "'interactive'" in text and "'service'" in text, (
        "one script, two modes: -Mode interactive|service, so the inverse "
        "always ships with the switch and neither becomes the next ad-hoc "
        "orphan."
    )
    assert "RUNNER_WIN_ROOT" in text and "USERPROFILE" in text, (
        "runner root from -RunnerRoot/RUNNER_WIN_ROOT with a USERPROFILE default."
    )
    assert "absin" not in text.lower(), (
        "no hard-coded user: the predecessor script was host-hardcoded and "
        "that is exactly why it got lost."
    )


def test_mode_switch_shares_the_elevation_conventions() -> None:
    """Same UAC contract as install_runner_svc_win.ps1: forward args (env
    does not survive UAC), transcript (the elevated console dies on exit),
    catch the declined prompt."""
    text = _text()
    assert "-Verb RunAs" in text and "-Wait" in text and "ExitCode" in text
    assert "'-RunnerRoot'" in text and "'-Mode'" in text, (
        "forward -Mode and -RunnerRoot to the elevated child explicitly."
    )
    assert "Start-Transcript" in text
    assert re.search(r"catch", text, re.IGNORECASE)


def test_mode_switch_refuses_to_kill_a_running_job() -> None:
    text = _text()
    assert "Runner.Worker" in text, (
        "both directions stop the live runner; abort while a job executes "
        "(-Force to override)."
    )


def test_interactive_mode_shape() -> None:
    """The decisions that make GUI e2e work and survive the next reboot."""
    text = _text()
    assert "run.cmd" in text, "interactive mode runs the runner's own run.cmd."
    assert "AtLogOn" in text, (
        "a logon trigger brings the runner back with the user's session "
        "after a reboot (with auto-logon, unattended too)."
    )
    assert "Interactive" in text, (
        "the task principal must be the current user's INTERACTIVE logon - "
        "Session 0 is the whole bug."
    )
    assert re.search(r"ExecutionTimeLimit.*Zero|-ExecutionTimeLimit 0", text), (
        "Task Scheduler kills tasks after 3 days by default; the runner "
        "must run indefinitely (ExecutionTimeLimit zero)."
    )
    assert "'disabled'" in text.lower() or "start= disabled" in text, (
        "the service must be Disabled, not just stopped - delayed-auto "
        "would resurrect Session 0 at the next reboot (the lived failure)."
    )
    assert "SessionId" in text, (
        "prove the fix: the started listener's SessionId must not be 0."
    )


def test_service_mode_is_the_inverse() -> None:
    text = _text()
    assert "Unregister-ScheduledTask" in text, (
        "service mode must remove the logon task or two runners race."
    )
    assert "delayed-auto" in text, (
        "service mode re-enables delayed-auto (reboot survival without a logon)."
    )


def test_justfile_wires_both_modes() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    for recipe in ("runner-mode-interactive", "runner-mode-service"):
        m = re.search(rf"^\[([^\]]*)\]\s*\n{recipe}:", text, re.MULTILINE)
        assert m is not None, f"justfile must define {recipe}."
        assert "windows" in m.group(1) and "Disk" in m.group(1), (
            f"{recipe}: [windows]-gated, grouped with the runner recipes."
        )


def test_status_recognises_deliberate_interactive_mode() -> None:
    """A listener outside the service was a WARN ('run.cmd mode?'). When the
    dotfiles logon task exists, the mode is DELIBERATE and must read OK —
    otherwise the false alarm trains the reader to ignore the line, which is
    how the last mode switch got silently reverted."""
    text = STATUS.read_text(encoding="utf-8")
    assert "dotfiles-runner-interactive" in text, (
        "status must check for the interactive-mode logon task and report "
        "the mode as OK when it is deliberate."
    )


def test_interactive_mode_reowns_foreign_work_checkouts() -> None:
    r"""Live incident (2026-08-21): after the switch to interactive mode,
    vrt jobs died in actions/checkout within a second — the _work checkout
    dirs (comfy/SHAKU/vivo) were still owned by BUILTIN\Administrators from
    the LocalSystem-service era, and git's dubious-ownership check refuses a
    repo whose OWNER differs from the running user. The mirror image is
    already handled (install_runner_svc_win.ps1 warns about user-owned trees
    under SYSTEM); the interactive path must repair, not just warn — the
    switch itself created the mismatch, so it owns the cleanup.

    takeown without /A assigns ownership to the CURRENT (elevated) user,
    which is exactly the runner account here; job-runner dirs only, never
    the runner-internal _actions/_temp/_tool/_update/_PipelineMapping.
    """
    text = MODE.read_text(encoding="utf-8")
    assert "takeown" in text, (
        "interactive mode must re-own Administrators-owned _work checkouts "
        "to the runner user (git dubious-ownership)."
    )
    assert "/A" not in text.split("takeown", 1)[1].splitlines()[0], (
        "takeown must NOT use /A — that assigns to Administrators, which is "
        "the broken state being repaired."
    )
    assert "_PipelineMapping" in text, (
        "runner-internal dirs are enumerated and skipped, not re-owned."
    )


# --- watchdog (2026-09-03, third live report) --------------------------------
# The interactive listener died silently mid-day (gpu-win: _diag ends at
# 16:24:16Z with no shutdown line, no Application event, Task Scheduler
# history disabled) and nothing restarted it until the next logon - the
# logon task has no restart policy and run.cmd exits 0 on "terminated".
# A second start path (the legacy Startup .lnk) also raced the task at logon
# ("A session for this runner already exists", 2026-08-30). Prevention:
# a repo-managed watchdog task that re-fires the logon task when no listener
# lives, removal of the legacy .lnk, and Task Scheduler history ON so the
# next death has a cause.

WATCHDOG = SCRIPTS / "runner_watchdog_win.ps1"


def _watchdog() -> str:
    return WATCHDOG.read_text(encoding="utf-8")


def test_watchdog_exists_and_is_generic() -> None:
    assert WATCHDOG.is_file(), "scripts/runner_watchdog_win.ps1 is missing"
    text = _watchdog()
    assert "absin" not in text.lower(), (
        "no hard-coded user (same rule as the mode switch)"
    )
    assert (
        "dotfiles-runner-watchdog" in text and "dotfiles-runner-interactive" in text
    ), (
        "the watchdog re-fires the logon task by name; both task names spelled once here."
    )
    assert "Runner.Listener" in text and "Start-ScheduledTask" in text, (
        "the only action is: no Runner.Listener alive -> Start-ScheduledTask of the "
        "interactive task. It never kills anything."
    )
    assert "Stop-Process" not in text and "taskkill" not in text, (
        "a watchdog that kills is a second way to lose an in-flight job."
    )
    assert "-Install" in text and "Unregister-ScheduledTask" in text, (
        "self-installing (-Install registers the repeating task; idempotent re-register)."
    )
    assert "IgnoreNew" in text, (
        "overlapping firings collapse to one (duplicate-start valve)."
    )


def test_watchdog_writes_a_log_line_on_every_restart() -> None:
    """Silence is the failure mode we are fixing; each restart must leave a
    dated line so the NEXT death has a timestamp even if history is off."""
    text = _watchdog()
    assert "runner-watchdog-win.log" in text
    assert re.search(r"Get-Date", text)


def test_watchdog_task_runs_a_copy_outside_the_working_tree() -> None:
    """Lived 2026-09-03 02:18/02:23: the task pointed at the repo file, a branch
    switch removed it, and two ticks died with exit 0xFFFD0000 (-File not found)
    and no log line - the watchdog itself was the silent one."""
    text = _watchdog()
    assert "LOCALAPPDATA" in text and "Copy-Item" in text, (
        r"-Install copies the script to %LOCALAPPDATA%\dotfiles; the task runs the copy."
    )
    assert re.search(r'-File "\{0\}"[^\n]*-f \$installed', text), (
        "the task action's -File is the installed copy, never $PSCommandPath."
    )
    assert "-f $PSCommandPath" not in text


def test_mode_switch_wires_the_watchdog_and_removes_the_legacy_lnk() -> None:
    text = _text()
    assert "runner_watchdog_win.ps1" in text and "-Install" in text, (
        "-Mode interactive installs the watchdog; the switch is the one place the "
        "interactive stack is assembled."
    )
    assert "dotfiles-runner-watchdog" in text, (
        "-Mode service unregisters the watchdog too (else it would resurrect the "
        "interactive listener next to the service)."
    )
    assert ".lnk" in text and "Startup" in text, (
        "remove the legacy Startup shortcut (the pre-repo script's start path): two "
        "start paths race at logon -> 'A session for this runner already exists'."
    )
    assert (
        "Microsoft-Windows-TaskScheduler/Operational" in text and "/e:true" in text
    ), (
        "enable Task Scheduler history while elevated - without it a dead task "
        "leaves no trace (lived 2026-09-03)."
    )


def test_watchdog_install_keeps_a_task_it_cannot_replace() -> None:
    """Lived 2026-09-08: `just runner-watchdog-install` re-run on a box where
    runner-mode-interactive (elevated) had already registered the watchdog
    died with Register-ScheduledTask HRESULT 0x800700b7 ("already exists").
    The preceding Unregister ran with -ErrorAction SilentlyContinue, so a
    task the unelevated caller is not allowed to delete simply survived -
    and the installer then collided with it instead of noticing.

    Same contract as install_runner_gc_win.ps1's keepGcTask path: after the
    Unregister attempt, check whether the task is still there; if so, keep
    it as-is (say so) and skip re-registration - the watchdog is already in
    force, and a re-run must never turn a healthy box red.
    """
    text = WATCHDOG.read_text(encoding="utf-8")
    m = re.search(
        r"Unregister-ScheduledTask -TaskName \$watchTask[^\r\n]*\s(.*?)Register-ScheduledTask -TaskName \$watchTask",
        text,
        re.S,
    )
    assert m is not None, "expected the watchdog unregister/register pair"
    between = m.group(1)
    assert "Get-ScheduledTask -TaskName $watchTask" in between, (
        "after the (silently failing) Unregister, probe whether the task still "
        "exists before trying to Register it again."
    )
    assert re.search(r"keeping it as-is|cannot be replaced unelevated", between), (
        "an unremovable existing task is kept, not fought: say so and skip."
    )
