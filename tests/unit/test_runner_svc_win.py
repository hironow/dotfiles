"""The native Windows runner SERVICE must be repo-managed, like the WSL leg.

Found live (2026-08-20): service `actions.runner.m4k3-co.gpu-win` sat
Stopped + StartType=Disabled for an unknown stretch — GitHub showed the
runner offline and nothing on the host said so. The install/restart helpers
lived as ad-hoc scripts inside the runner directory (unversioned, host
hard-coded), so every machine reinvents them and none of the status tooling
knows the service exists.

History that shapes the requirements (see memory/ADR 0035 context):
- The service runs as **LocalSystem**, whose PATH is the *Machine* PATH.
  This box needed three Machine PATH appends (scoop shims, .bun\\bin, mise
  shims) before jobs could find their tools — the "PATH onion". The installer
  must verify those entries and point at scripts/restore_machine_path.ps1,
  not silently install a runner whose jobs die on `command not found`.
- PowerShell 5.1 reads a BOM-less UTF-8 script as ANSI, so the ps1 payloads
  must stay ASCII-only to survive a cp932 console.
- Service creation needs Administrator; the repo convention is UAC
  self-elevation (Start-Process -Verb RunAs, exit with the child's code),
  as in scripts/restore_machine_path.ps1.

Static text assertions, matching tests/unit/test_runner_gc.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
SVC = SCRIPTS / "install_runner_svc_win.ps1"
STATUS = SCRIPTS / "gc_status.sh"
JUSTFILE = ROOT / "justfile"


def _text() -> str:
    return SVC.read_text(encoding="utf-8")


RESTART = SCRIPTS / "restart_runner_svc_win.ps1"


def test_installer_exists() -> None:
    assert SVC.is_file(), "scripts/install_runner_svc_win.ps1 is missing"
    assert RESTART.is_file(), "scripts/restart_runner_svc_win.ps1 is missing"
    # ASCII-only is covered by the glob test in test_runner_gc.py.


def test_installer_is_generic_not_this_host() -> None:
    """Any Windows box must be able to adopt it: root from RUNNER_WIN_ROOT
    (default under USERPROFILE), names derived from the runner's own .runner
    JSON — never a hard-coded user or service name."""
    text = _text()
    assert "RUNNER_WIN_ROOT" in text and "USERPROFILE" in text, (
        "the runner root must come from RUNNER_WIN_ROOT with a USERPROFILE default."
    )
    assert re.search(r"\.runner", text) and "agentName" in text, (
        "the service name must be derived from the .runner config "
        "(gitHubUrl owner + agentName), not typed in."
    )
    assert "absin" not in text.lower(), (
        "no hard-coded user: the script must work on any Windows host."
    )


def test_installer_refuses_an_unconfigured_runner() -> None:
    """No .runner file = the runner was never configured on this box; the
    installer must say so and stop, not create a service pointing at air."""
    text = _text()
    assert re.search(r"Join-Path .*'\.runner'", text) and "Test-Path" in text, (
        "the installer must check the .runner config exists before touching services."
    )
    assert "not configured" in text, (
        "the missing-.runner branch must say the runner is not configured and stop."
    )


def test_installer_self_elevates_and_propagates_the_exit_code() -> None:
    for path in (SVC, RESTART):
        text = path.read_text(encoding="utf-8")
        assert "-Verb RunAs" in text, (
            f"{path.name}: service control needs Administrator; repo "
            "convention is UAC self-elevation (see restore_machine_path.ps1)."
        )
        assert "-Wait" in text and "ExitCode" in text, (
            f"{path.name}: the non-elevated parent must wait for the elevated "
            "child and exit with ITS code."
        )
        # B1: the elevated child gets a fresh console that vanishes on exit
        # and does not reliably inherit the caller's env. The root must be
        # forwarded as an explicit argument and the output must survive in a
        # transcript whose path the parent printed BEFORE elevating.
        assert "-RunnerRoot" in text, (
            f"{path.name}: forward the runner root to the elevated child as "
            "an explicit -RunnerRoot argument (env vars do not survive UAC)."
        )
        assert "Start-Transcript" in text, (
            f"{path.name}: the elevated child's console closes on exit; a "
            "transcript is the only surviving output."
        )
        # S9: a declined UAC prompt throws; it must fail legibly.
        assert re.search(r"catch", text, re.IGNORECASE), (
            f"{path.name}: catch the declined-UAC exception and exit "
            "non-zero with a message."
        )


def test_sc_exit_codes_are_checked() -> None:
    """B2: $ErrorActionPreference='Stop' ignores native exit codes; a failed
    sc.exe create surfaces later as a confusing 'cannot find service'."""
    text = _text()
    assert "LASTEXITCODE" in text, (
        "check $LASTEXITCODE after sc.exe calls and fail with the output."
    )


def test_restart_refuses_to_kill_a_running_job() -> None:
    """B4: restarting the service kills an in-flight job; the script must
    abort when Runner.Worker exists (like fix-work-ownership.ps1 does)."""
    text = RESTART.read_text(encoding="utf-8")
    assert "Runner.Worker" in text, (
        "check for a running Runner.Worker before restarting."
    )


def test_installer_service_shape() -> None:
    """LocalSystem + delayed-auto + failure recovery: the decisions that make
    the runner survive reboots and transient crashes unattended."""
    text = _text()
    assert "LocalSystem" in text, "run as LocalSystem (no storable password)."
    assert "delayed-auto" in text, (
        "delayed-auto start: the runner must come back after a reboot "
        "without racing the network stack."
    )
    assert "restart/60000" in text and "'failure'" in text, (
        "configure failure recovery (auto-restart via sc.exe failure)."
    )
    assert "failureflag" in text, (
        "sc.exe failureflag 1: without it recovery only fires on a crash, "
        "not on the runner exiting non-zero — the case that matters."
    )
    assert "'config'" in text, (
        "an existing-but-Disabled service must be re-enabled in place via "
        "sc.exe config (Set-Service cannot express delayed-auto)."
    )
    assert re.search(r"replace\('/'", text) or re.search(r"-replace\s*'/'", text), (
        "repo-scoped runners give gitHubUrl=owner/repo; '/' is illegal in a "
        "service name and must be normalised to '-'."
    )


def test_installer_warns_about_localsystem_work_ownership() -> None:
    """B5: _work trees owned by the interactive user fail git's dubious-
    ownership check when the service runs as SYSTEM. The installer must at
    least detect and teach the fix, not let the next job discover it."""
    text = _text()
    assert "_work" in text and ("safe.directory" in text or "takeown" in text), (
        "detect user-owned _work under a LocalSystem service and print the "
        "repair (takeown / git safe.directory)."
    )


def test_installer_verifies_the_machine_path_onion() -> None:
    """LocalSystem resolves tools via the MACHINE PATH. This box needed scoop
    shims + .bun\\bin + mise shims appended there before jobs stopped dying on
    `command not found` — and the failure is silent (jobs fail, service looks
    healthy). The installer must check and teach the fix."""
    text = _text()
    for needle in ("scoop", "bun", "mise"):
        assert needle in text, (
            f"Machine PATH verification must cover the {needle} entry of the "
            "PATH onion."
        )
    assert "restore_machine_path.ps1" in text, (
        "point at scripts/restore_machine_path.ps1 for the repair, do not "
        "reimplement it."
    )
    # B6: PATH presence proves findable, not usable — SYSTEM's %LOCALAPPDATA%
    # holds none of the per-user tool state. The green line must not oversell.
    assert "SYSTEM" in text, (
        "the PATH check wording must note that per-user tool state is not "
        "visible to SYSTEM; proof is the next green job."
    )


def test_justfile_wires_the_service_recipes() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    for recipe in ("runner-svc-install", "runner-svc-restart"):
        m = re.search(rf"^\[([^\]]*)\]\s*\n{recipe}:", text, re.MULTILINE)
        assert m is not None, f"justfile must define a [windows] {recipe} recipe."
        assert "windows" in m.group(1), (
            f"{recipe} manages a Windows service; it must be [windows]-gated."
        )
        assert "Disk" in m.group(1), (
            f"{recipe} belongs with the runner-gc recipes in group('Disk') — "
            "just status (Disk) is what reports the service."
        )


def test_status_surfaces_a_stopped_or_disabled_service() -> None:
    """The whole incident was 'nothing on the host said the runner was off'.
    `just status` must show the service state and treat Stopped/Disabled as a
    failure with the fix spelled out."""
    text = STATUS.read_text(encoding="utf-8")
    assert "Get-Service" in text, (
        "gc_status.sh must query the native runner service state."
    )
    # S5: the host deliberately toggles between service mode and interactive
    # run.cmd mode; a bare "service Stopped" FAIL would be a standing false
    # alarm. Judge on effect: FAIL only when the service is not Running AND
    # no Runner.Listener process exists.
    assert "Runner.Listener" in text, (
        "status must only FAIL when neither the service runs nor a "
        "Runner.Listener process exists (interactive run.cmd mode)."
    )
    assert "Disabled" in text, (
        "StartType=Disabled is the silent killer found live; status must "
        "call it out explicitly."
    )
    assert "runner-svc-install" in text, (
        "the failure line must teach the fix: just runner-svc-install."
    )
