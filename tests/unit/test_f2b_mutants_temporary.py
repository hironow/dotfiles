"""TEMPORARY (removed before merge): each D4 behavior test of this pull
request fails when its guard is broken.

Each case copies the scripts, breaks one guard in the copy, runs the same
check the real test runs on the copy, and expects the check to fail.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import test_bootstrap_ps1 as boot
import test_runner_task_installers as inst
import test_wsl_autostart as auto

ROOT = Path(__file__).resolve().parents[2]

BOOT = [
    ("origin check removed", boot.check_stranger_clone_is_refused,
     "if ($origin -notmatch 'hironow/dotfiles') {", "if ($false) {"),
    ("policy for the machine", boot.check_strict_policy_is_lowered_for_the_user_only,
     "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force", "Set-ExecutionPolicy -Scope LocalMachine Unrestricted -Force"),
    ("policy always set", boot.check_open_policy_is_left_alone,
     "if ($policy -notin @('Unrestricted', 'RemoteSigned', 'Bypass')) {", "if ($true) {"),
]  # fmt: skip

AUTO = [
    ("probe finds itself", auto.check_no_keepalive_attaches_one, "dotfiles-wsl-keepaliv[e]", "dotfiles-wsl-keepalive"),
    ("valve A ignored", auto.check_a_live_keepalive_is_not_doubled,
     "if ($LASTEXITCODE -eq 0) {\n    Write-Log \"a keepalive client is already attached", "if ($false) {\n    Write-Log \"a keepalive client is already attached"),
]  # fmt: skip

GC, WD = "install_runner_gc_win.ps1", "runner_watchdog_win.ps1"
WIN = [
    ("autostart overlaps", inst.check_gc_install_registers_one_autostart, GC,
     "-MultipleInstances IgnoreNew", "-MultipleInstances Parallel"),
    ("installer stops the keepalive", inst.check_gc_install_registers_one_autostart, GC,
     "Start-ScheduledTask -TaskName $AutostartTaskName", "Stop-ScheduledTask -TaskName $AutostartTaskName -ErrorAction SilentlyContinue\nStart-ScheduledTask -TaskName $AutostartTaskName"),
    ("a denied unregister goes on to register", inst.check_gc_install_keeps_what_it_cannot_replace, GC,
     "Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop", "Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Continue"),
    ("installer removes before the copy", inst.check_gc_install_removes_nothing_without_a_launcher, GC,
     ". (Join-Path $here 'run_hidden_win.ps1')", "Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue\n. (Join-Path $here 'run_hidden_win.ps1')"),
    ("watchdog overlaps", inst.check_watchdog_install_registers_one_watchdog, WD,
     "-MultipleInstances IgnoreNew", "-MultipleInstances Parallel"),
    ("watchdog removes before the copy", inst.check_watchdog_install_removes_nothing_without_a_launcher, WD,
     "    . (Join-Path $PSScriptRoot 'run_hidden_win.ps1')", "    Unregister-ScheduledTask -TaskName $watchTask -Confirm:$false -ErrorAction SilentlyContinue\n    . (Join-Path $PSScriptRoot 'run_hidden_win.ps1')"),
    ("watchdog ignores a live listener", inst.check_watchdog_fires_the_runner_only_when_the_listener_is_gone, WD,
     "if ($listener) {", "if ($false) {"),
    ("watchdog stops the runner task", inst.check_watchdog_fires_the_runner_only_when_the_listener_is_gone, WD,
     "Start-ScheduledTask -TaskName $runnerTask", "Stop-ScheduledTask -TaskName $runnerTask -ErrorAction SilentlyContinue\nStart-ScheduledTask -TaskName $runnerTask"),
]  # fmt: skip


def _broken(source: Path, dest: Path, old: str, new: str) -> Path:
    text = source.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"{source.name}: anchor found {text.count(old)} times: {old!r}"
    )
    dest.write_text(text.replace(old, new), encoding="utf-8")
    return dest


@pytest.mark.skipif(boot.PWSH is None, reason="needs PowerShell")
@pytest.mark.parametrize(
    ("name", "check", "old", "new"), BOOT, ids=[c[0] for c in BOOT]
)
def test_bootstrap_guard_breaks_are_caught(
    tmp_path: Path, name: str, check, old: str, new: str
) -> None:
    script = _broken(ROOT / "bootstrap.ps1", tmp_path / "bootstrap.ps1", old, new)
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(AssertionError):
        check(run, script)


@pytest.mark.skipif(auto.PWSH is None, reason="needs pwsh")
@pytest.mark.parametrize(
    ("name", "check", "old", "new"), AUTO, ids=[c[0] for c in AUTO]
)
def test_autostart_guard_breaks_are_caught(
    tmp_path: Path, name: str, check, old: str, new: str
) -> None:
    script = _broken(
        ROOT / "scripts" / "wsl_autostart.ps1", tmp_path / "wsl_autostart.ps1", old, new
    )
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(AssertionError):
        check(run, script)


@pytest.mark.skipif(inst.PWSH is None, reason="native Windows with PowerShell only")
@pytest.mark.parametrize(
    ("name", "check", "file", "old", "new"), WIN, ids=[c[0] for c in WIN]
)
def test_task_installer_guard_breaks_are_caught(
    tmp_path: Path, name: str, check, file: str, old: str, new: str
) -> None:
    scripts = tmp_path / "scripts"
    shutil.copytree(
        ROOT / "scripts", scripts, ignore=shutil.ignore_patterns("__pycache__")
    )
    _broken(ROOT / "scripts" / file, scripts / file, old, new)
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(AssertionError):
        check(run, scripts)
