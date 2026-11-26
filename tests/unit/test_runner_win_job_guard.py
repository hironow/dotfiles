"""The Windows runner's mode switch and service restart refuse to kill a job.

ADR-0093 D4: a concurrency guard is held by a test that runs the code. Both
scripts check for Runner.Worker before they elevate or touch a service, so the
check runs under pwsh on any OS: a wrapper defines functions that shadow the
cmdlets the scripts reach first (functions win over cmdlets), records any call
that would stop the runner, and starts the real script with a synthetic runner
root. A live worker must stop the run with exit 1 and the reason, before any
elevation or service call. The refusal is printed only by the guard, so the test
fails if the guard goes. There is no idle case: past the guard the scripts act on
the host's services and scheduled tasks, which a test must not reach.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
MODE = ROOT / "scripts" / "runner_mode_win.ps1"
RESTART = ROOT / "scripts" / "restart_runner_svc_win.ps1"
PWSH = resolve_pwsh(os.environ)
REFUSAL = "a job is executing"

pytestmark = pytest.mark.skipif(PWSH is None, reason="needs pwsh to run the scripts")


def _runner(tmp_path: Path) -> Path:
    root = tmp_path / "runner"
    root.mkdir()
    (root / ".runner").write_text(
        json.dumps({"gitHubUrl": "https://github.com/example-org", "agentName": "box"}),
        encoding="utf-8",
    )
    (root / "run.cmd").write_text("@echo off\r\n", encoding="utf-8")
    return root


def _run(
    tmp_path: Path, script: Path, args: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    assert PWSH is not None
    log = tmp_path / "stops.log"
    log.touch()
    worker_object = "[pscustomobject]@{ Id = 4242; ProcessName = 'Runner.Worker' }"
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(
        f"""$ErrorActionPreference = 'Stop'
function Get-Process {{
    param([string[]]$Name, $ErrorAction)
    if ($Name -contains 'Runner.Worker') {{ return {worker_object} }}
    return $null
}}
function Get-Service {{ param($Name, $ErrorAction) [pscustomobject]@{{ Name = $Name; Status = 'Running' }} }}
function Record([string]$What) {{ Add-Content -LiteralPath '{log}' -Value $What }}
function Restart-Service {{ Record 'Restart-Service'; throw 'the runner was restarted' }}
function Stop-Service {{ Record 'Stop-Service'; throw 'the runner was stopped' }}
function Start-Process {{ Record 'Start-Process'; throw 'elevation was attempted' }}
& '{script}' {args}
exit $LASTEXITCODE
""",
        encoding="utf-8",
    )
    env = {**os.environ, "TEMP": str(tmp_path), "TMP": str(tmp_path)}
    env.pop("RUNNER_WIN_ROOT", None)
    done = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(wrapper)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
        timeout=60,
    )
    return done, log.read_text(encoding="utf-8").split()


CASES = {
    "mode switch": (MODE, "-Mode interactive -RunnerRoot '{root}'"),
    "service restart": (RESTART, "-RunnerRoot '{root}'"),
}


@pytest.mark.parametrize("name", CASES)
def test_a_live_job_stops_the_run(tmp_path: Path, name: str) -> None:
    script, args = CASES[name]
    done, stops = _run(tmp_path, script, args.format(root=_runner(tmp_path)))
    output = done.stdout + done.stderr
    assert done.returncode == 1, output
    assert REFUSAL in output, output
    assert stops == [], stops
