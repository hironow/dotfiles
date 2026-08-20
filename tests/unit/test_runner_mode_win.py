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
