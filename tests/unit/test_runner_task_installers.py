"""The Windows task installers keep running tasks running (ADR-0093 D4).

install_runner_gc_win.ps1 registers the GC task and the WSL autostart task;
runner_watchdog_win.ps1 registers the watchdog and, on each tick, re-fires
the interactive runner task. Their concurrency and update guards are held
here by running copies of the scripts:

- the autostart and watchdog tasks collapse overlapping starts (IgnoreNew);
- nothing ever stops a running task or process (the keepalive, a job);
- an unelevated re-run keeps a task it cannot replace and goes on;
- a launcher (run-hidden.exe) that cannot be copied stops the run before
  any task is removed;
- the watchdog fires the runner task only when Runner.Listener is gone.

Native Windows only: the scripts need the ScheduledTasks module and a Windows
identity. The wrapper imports ScheduledTasks first (its commands are module
functions, and an auto-import would replace same-named functions), then
shadows every command that could change the machine with a global function
that records the call, checks that each shadow is the one that resolves, and
only then starts the script. TEMP, LOCALAPPDATA, APPDATA and USERPROFILE
point into the test's folder. The GC installer stops at Start-ScheduledTask,
before it writes a runner's .env.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
NEEDED = (
    "install_runner_gc_win.ps1",
    "run_hidden_win.ps1",
    "runner_gc_win.ps1",
    "wsl_autostart.ps1",
    "runner_watchdog_win.ps1",
)
PWSH = (
    (resolve_pwsh(os.environ) or shutil.which("powershell"))
    if sys.platform == "win32"
    else None
)
GC_TASK = "dotfiles-runner-gc"
AUTOSTART_TASK = "dotfiles-wsl-autostart"
WATCH_TASK = "dotfiles-runner-watchdog"
RUNNER_TASK = "dotfiles-runner-interactive"

pytestmark = pytest.mark.skipif(
    PWSH is None, reason="native Windows with PowerShell only"
)

WRAPPER = r"""
$ErrorActionPreference = 'Stop'
Import-Module ScheduledTasks
$global:S = Get-Content -Raw -LiteralPath '__SETTINGS__' | ConvertFrom-Json
$global:Calls = [System.Collections.Generic.List[string]]::new()
function global:Record([string]$What) { $global:Calls.Add($What) }
function global:Get-ScheduledTask {
    [CmdletBinding()]
    param([string]$TaskName)
    if (@($global:S.existing) -contains $TaskName) {
        return [pscustomobject]@{ TaskName = $TaskName; State = 'Ready' }
    }
}
function global:Unregister-ScheduledTask {
    [CmdletBinding(SupportsShouldProcess)]
    param([string]$TaskName)
    Record "Unregister $TaskName"
    if ($global:S.denyUnregister) { Write-Error 'Access is denied.' }
}
function global:Register-ScheduledTask {
    [CmdletBinding()]
    param([string]$TaskName, $Action, $Trigger, $Settings, $Principal, [string]$Description)
    Record ("Register $TaskName MultipleInstances=" + $(if ($Settings) { $Settings.MultipleInstances }))
    [pscustomobject]@{ TaskName = $TaskName }
}
function global:Start-ScheduledTask {
    [CmdletBinding()]
    param([string]$TaskName)
    Record "Start $TaskName"
    if ($global:S.stopAtStart) { throw 'EXPECTED the boundary before the .env step' }
}
function global:Stop-ScheduledTask { Record ('Stop-ScheduledTask ' + ($args -join ' ')); throw 'UNEXPECTED Stop-ScheduledTask' }
function global:Stop-Process { Record ('Stop-Process ' + ($args -join ' ')); throw 'UNEXPECTED Stop-Process' }
function global:taskkill { Record ('taskkill ' + ($args -join ' ')); throw 'UNEXPECTED taskkill' }
function global:Start-Process { Record ('Start-Process ' + ($args -join ' ')); throw 'UNEXPECTED Start-Process' }
function global:wevtutil { Record ('wevtutil ' + ($args -join ' ')); $global:LASTEXITCODE = 5 }
function global:Start-Sleep { param($Seconds) }
function global:Get-Process {
    [CmdletBinding()]
    param([string[]]$Name)
    $started = @($global:Calls | Where-Object { $_ -like 'Start *' }).Count -gt 0
    if ($Name -contains 'Runner.Listener' -and ($global:S.listener -or ($started -and $global:S.listenerAfterStart))) {
        return [pscustomobject]@{ Id = 4242; SessionId = 1; ProcessName = 'Runner.Listener' }
    }
}
$shadows = @('Get-ScheduledTask', 'Unregister-ScheduledTask', 'Register-ScheduledTask', 'Start-ScheduledTask',
    'Stop-ScheduledTask', 'Stop-Process', 'taskkill', 'Start-Process', 'wevtutil', 'Start-Sleep', 'Get-Process')
foreach ($n in $shadows) {
    $c = Get-Command -Name $n
    if ($c.CommandType -ne 'Function' -or $c.Module) { throw "SHADOW FAILED $n resolves to $($c.CommandType) $($c.Source)" }
}
$global:LASTEXITCODE = 0
try {
    & '__SCRIPT__' __ARGS__
    Record "exit $LASTEXITCODE"
} catch {
    if ($_.Exception.Message -like 'EXPECTED*') { Record 'stopped before the .env step' }
    else { Record ('error: ' + $_.Exception.Message) }
}
'RECEIPT=' + (ConvertTo-Json -InputObject @($global:Calls) -Compress)
"""


def run_script(
    tmp_path: Path,
    scripts: Path,
    name: str,
    args: str,
    *,
    existing: list[str],
    deny_unregister: bool = False,
    built: bool = True,
    listener: bool = False,
    listener_after_start: bool = False,
    stop_at_start: bool = False,
) -> list[str]:
    """Run a copy of scripts/<name> and return the calls it made."""
    assert PWSH is not None
    copy = tmp_path / "repo" / "scripts"
    copy.mkdir(parents=True)
    for script in NEEDED:
        shutil.copy(scripts / script, copy / script)
    if built:
        exe = tmp_path / "repo" / "output" / "run-hidden" / "run-hidden.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ not a real launcher")
    runner = tmp_path / "runner"
    runner.mkdir()
    (runner / "run.cmd").write_text("@echo off\r\n", encoding="utf-8")
    home = tmp_path / "home"
    for sub in ("Temp", "Local", "Roaming"):
        (home / sub).mkdir(parents=True)
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "existing": existing,
                "denyUnregister": deny_unregister,
                "listener": listener,
                "listenerAfterStart": listener_after_start,
                "stopAtStart": stop_at_start,
            }
        ),
        encoding="utf-8",
    )
    if name == "runner_watchdog_win.ps1":
        args = f"{args} -RunnerRoot '{runner}'"
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(
        WRAPPER.replace("__SETTINGS__", str(settings))
        .replace("__SCRIPT__", str(copy / name))
        .replace("__ARGS__", args),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "TEMP": str(home / "Temp"),
        "TMP": str(home / "Temp"),
        "LOCALAPPDATA": str(home / "Local"),
        "APPDATA": str(home / "Roaming"),
        "USERPROFILE": str(home),
    }
    env.pop("RUNNER_WIN_ROOT", None)
    env.pop("RUNNER_GC_WSL_DISTRO", None)
    done = subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
        env=env,
    )
    receipt = [line for line in done.stdout.splitlines() if line.startswith("RECEIPT=")]
    assert done.returncode == 0 and receipt, done.stdout + done.stderr
    return json.loads(receipt[-1].removeprefix("RECEIPT="))


def _no_stops(calls: list[str]) -> None:
    stops = [
        c
        for c in calls
        if c.split(" ")[0] in ("Stop-ScheduledTask", "Stop-Process", "taskkill")
    ]
    assert not stops, calls


def check_gc_install_registers_one_autostart(tmp_path: Path, scripts: Path) -> None:
    calls = run_script(
        tmp_path,
        scripts,
        "install_runner_gc_win.ps1",
        "-Distro Ubuntu",
        existing=[],
        stop_at_start=True,
    )
    assert f"Register {AUTOSTART_TASK} MultipleInstances=IgnoreNew" in calls, calls
    assert calls[-1] == "stopped before the .env step", calls
    _no_stops(calls)


def check_gc_install_keeps_what_it_cannot_replace(
    tmp_path: Path, scripts: Path
) -> None:
    calls = run_script(
        tmp_path,
        scripts,
        "install_runner_gc_win.ps1",
        "-Distro Ubuntu",
        existing=[GC_TASK, AUTOSTART_TASK],
        deny_unregister=True,
        stop_at_start=True,
    )
    assert (
        f"Unregister {GC_TASK}" in calls and f"Unregister {AUTOSTART_TASK}" in calls
    ), calls
    assert not [c for c in calls if c.startswith("Register ")], calls
    assert (
        f"Start {AUTOSTART_TASK}" in calls
        and calls[-1] == "stopped before the .env step"
    ), calls
    _no_stops(calls)


def check_gc_install_removes_nothing_without_a_launcher(
    tmp_path: Path, scripts: Path
) -> None:
    calls = run_script(
        tmp_path,
        scripts,
        "install_runner_gc_win.ps1",
        "-Distro Ubuntu",
        existing=[GC_TASK, AUTOSTART_TASK],
        built=False,
        stop_at_start=True,
    )
    assert calls and calls[-1].startswith("error: run-hidden is not built"), calls
    assert not [c for c in calls if c.startswith(("Unregister ", "Register "))], calls


def check_watchdog_install_registers_one_watchdog(
    tmp_path: Path, scripts: Path
) -> None:
    calls = run_script(
        tmp_path, scripts, "runner_watchdog_win.ps1", "-Install", existing=[RUNNER_TASK]
    )
    assert f"Register {WATCH_TASK} MultipleInstances=IgnoreNew" in calls, calls
    assert calls[-1] == "exit 0", calls
    _no_stops(calls)


def check_watchdog_install_removes_nothing_without_a_launcher(
    tmp_path: Path, scripts: Path
) -> None:
    calls = run_script(
        tmp_path,
        scripts,
        "runner_watchdog_win.ps1",
        "-Install",
        existing=[RUNNER_TASK, WATCH_TASK],
        built=False,
    )
    assert calls[-1] == "exit 1", calls
    assert not [c for c in calls if c.startswith(("Unregister ", "Register "))], calls


def check_watchdog_fires_the_runner_only_when_the_listener_is_gone(
    tmp_path: Path, scripts: Path
) -> None:
    gone = tmp_path / "gone"
    gone.mkdir()
    calls = run_script(
        gone,
        scripts,
        "runner_watchdog_win.ps1",
        "",
        existing=[RUNNER_TASK],
        listener_after_start=True,
    )
    assert f"Start {RUNNER_TASK}" in calls and calls[-1] == "exit 0", calls
    _no_stops(calls)
    alive = tmp_path / "alive"
    alive.mkdir()
    calls = run_script(
        alive,
        scripts,
        "runner_watchdog_win.ps1",
        "",
        existing=[RUNNER_TASK],
        listener=True,
    )
    assert not [c for c in calls if c.startswith("Start ")] and calls[-1] == "exit 0", (
        calls
    )
    _no_stops(calls)


def test_the_gc_install_registers_one_autostart_and_stops_nothing(
    tmp_path: Path,
) -> None:
    check_gc_install_registers_one_autostart(tmp_path, SCRIPTS)


def test_an_unelevated_gc_install_keeps_tasks_it_cannot_replace(tmp_path: Path) -> None:
    check_gc_install_keeps_what_it_cannot_replace(tmp_path, SCRIPTS)


def test_the_gc_install_removes_nothing_without_a_launcher(tmp_path: Path) -> None:
    check_gc_install_removes_nothing_without_a_launcher(tmp_path, SCRIPTS)


def test_the_watchdog_install_registers_one_watchdog_and_stops_nothing(
    tmp_path: Path,
) -> None:
    check_watchdog_install_registers_one_watchdog(tmp_path, SCRIPTS)


def test_the_watchdog_install_removes_nothing_without_a_launcher(
    tmp_path: Path,
) -> None:
    check_watchdog_install_removes_nothing_without_a_launcher(tmp_path, SCRIPTS)


def test_the_watchdog_fires_the_runner_only_when_the_listener_is_gone(
    tmp_path: Path,
) -> None:
    check_watchdog_fires_the_runner_only_when_the_listener_is_gone(tmp_path, SCRIPTS)
