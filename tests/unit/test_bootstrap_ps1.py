"""The Windows bootstrap one-liner (ADR 0039): what it must keep, and the
guards that decide what it deploys and which policy it sets.

The checks of what bootstrap.ps1 says (HTTPS clone, no submodules, a login
Git Bash, the chain order, scoop out of process, winget's exit codes, ...)
are the `bootstrap-facts` rule of tools/repo-lint (ADR-0093). Two guards are
authorization, so they are held here by running the script (ADR-0093 D4):

- an existing ~/dotfiles whose origin is not hironow/dotfiles is never
  deployed from (the justfile hard-codes ~/dotfiles paths);
- the execution policy is lowered only for the current user, only to
  RemoteSigned, and only when it is stricter.

The runs use PowerShell (pwsh, or Windows PowerShell) with global functions
that shadow every command the script reaches before the Git Bash step, where
a fake `cmd` stops the run. Nothing is installed, cloned or changed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "bootstrap.ps1"
PWSH = resolve_pwsh(os.environ) or shutil.which("powershell")
OURS = "https://github.com/hironow/dotfiles.git"
STRANGER = "https://github.com/someone/dotfiles.git"

needs_pwsh = pytest.mark.skipif(
    PWSH is None, reason="needs PowerShell to run bootstrap.ps1"
)


def test_ascii_only() -> None:
    raw = BOOTSTRAP.read_bytes()
    assert all(b < 128 for b in raw), (
        "bootstrap.ps1 must be ASCII-only: PowerShell 5.1 reads BOM-less "
        "UTF-8 as ANSI, and irm|iex decodes without a charset — non-ASCII "
        "turns into mojibake on the exact machines bootstrap targets."
    )


def test_parses_as_valid_powershell() -> None:
    if PWSH is None:
        pytest.skip("no PowerShell available to parse-check bootstrap.ps1")
    check = (
        "$t=$null;$e=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{BOOTSTRAP}',[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count -gt 0){$e|ForEach-Object{$_.ToString()};exit 1}"
    )
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-Command", check],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, (
        "bootstrap.ps1 has PowerShell syntax errors:\n" + proc.stdout
    )


# Shadows for every command bootstrap.ps1 reaches before the Git Bash step.
# Functions win over cmdlets and programs; none of these names is a module
# function, so no auto-import can replace them. `cmd /c 'scoop prefix git'`
# is the boundary: the run stops there, before Git Bash and the just chain.
WRAPPER = r"""
$ErrorActionPreference = 'Stop'
$global:S = Get-Content -Raw -LiteralPath '__SETTINGS__' | ConvertFrom-Json
$global:Calls = [System.Collections.Generic.List[string]]::new()
function global:Record([string]$What) { $global:Calls.Add($What) }
$present = @('podman', 'scoop', 'git', 'just', 'jq', 'mise', 'pwsh')
function global:Get-Command {
    [CmdletBinding()]
    param([Parameter(Position = 0)][string]$Name)
    if ($Name -in @('podman', 'scoop', 'git', 'just', 'jq', 'mise', 'pwsh')) {
        return [pscustomobject]@{ Name = $Name; Source = "fake\$Name.exe" }
    }
    throw "UNEXPECTED Get-Command $Name"
}
function global:podman {
    $global:LASTEXITCODE = 0
    if (($args -join ' ') -ne '--version') { throw 'UNEXPECTED podman' }
    'podman version 5.8.0'
}
function global:Get-ExecutionPolicy {
    param([string]$Scope)
    Record "Get-ExecutionPolicy -Scope $Scope"
    $global:S.policy
}
function global:Set-ExecutionPolicy {
    param([Parameter(Position = 0)][string]$ExecutionPolicy, [string]$Scope, [switch]$Force)
    Record "Set-ExecutionPolicy -Scope $Scope $ExecutionPolicy"
}
function global:cmd {
    $line = $args -join ' '
    Record "cmd $line"
    if ($line -eq '/c scoop prefix just') { $global:LASTEXITCODE = 1; return }
    if ($line -eq '/c scoop prefix git') { throw 'EXPECTED the Git Bash step' }
    throw "UNEXPECTED cmd $line"
}
function global:just {
    if (($args -join ' ') -ne '--version') { throw 'UNEXPECTED just' }
    $global:LASTEXITCODE = 0
    'just 1.59.0'
}
function global:Test-Path {
    param([Parameter(Position = 0)][string]$Path)
    if ($Path -notlike '*dotfiles?.git') { throw "UNEXPECTED Test-Path $Path" }
    Record 'Test-Path the clone'
    [bool]$global:S.cloned
}
function global:git {
    $line = $args -join ' '
    Record "git $line"
    $global:LASTEXITCODE = 0
    if ($line -like '-C * remote get-url origin') { return $global:S.origin }
    if ($line -like 'clone *') { return }
    throw "UNEXPECTED git $line"
}
foreach ($n in @('Invoke-RestMethod', 'Invoke-Expression', 'Invoke-WebRequest', 'winget', 'Start-Process')) {
    Set-Item -Path "function:global:$n" -Value ([scriptblock]::Create("throw 'UNEXPECTED $n'"))
}
foreach ($n in @('Get-Command', 'podman', 'Get-ExecutionPolicy', 'Set-ExecutionPolicy', 'cmd', 'just', 'Test-Path', 'git', 'Invoke-RestMethod', 'Invoke-Expression', 'winget', 'Start-Process')) {
    $c = Microsoft.PowerShell.Core\Get-Command -Name $n -CommandType Function -ErrorAction SilentlyContinue
    if (-not $c -or $c.Module) { throw "SHADOW FAILED $n" }
}
try {
    & '__SCRIPT__'
    Record 'finished'
} catch {
    if ($_.Exception.Message -like 'EXPECTED*') { Record 'stopped at the Git Bash step' }
    else { Record ('error: ' + $_.Exception.Message) }
}
'RECEIPT=' + (ConvertTo-Json -InputObject @($global:Calls) -Compress)
"""


def _ps_literal(text: object) -> str:
    """Text for inside a PowerShell single-quoted string."""
    return str(text).replace("'", "''")


def run_bootstrap(
    tmp_path: Path,
    script: Path,
    *,
    origin: str,
    cloned: bool = True,
    policy: str = "RemoteSigned",
) -> list[str]:
    """Run `script` (bootstrap.ps1 or a copy) and return the calls it made."""
    assert PWSH is not None
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"origin": origin, "cloned": cloned, "policy": policy}),
        encoding="utf-8",
    )
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(
        WRAPPER.replace("__SETTINGS__", _ps_literal(settings)).replace(
            "__SCRIPT__", _ps_literal(script)
        ),
        # A BOM: Windows PowerShell 5.1 reads a BOM-less file as ANSI, and
        # the wrapper holds paths, which may not be ASCII.
        encoding="utf-8-sig",
    )
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
        timeout=120,
        env={**os.environ, "HOME": str(tmp_path), "DOTFILES_HOST": "windows"},
    )
    receipt = [line for line in done.stdout.splitlines() if line.startswith("RECEIPT=")]
    assert done.returncode == 0 and receipt, done.stdout + done.stderr
    return json.loads(receipt[-1].removeprefix("RECEIPT="))


def check_stranger_clone_is_refused(tmp_path: Path, script: Path) -> None:
    calls = run_bootstrap(tmp_path, script, origin=STRANGER)
    errors = [c for c in calls if c.startswith("error: ")]
    assert len(errors) == 1 and "refusing to deploy" in errors[0], calls
    assert "cmd /c scoop prefix git" not in calls, (
        "the run went on past the origin check"
    )
    assert not any(c.startswith("git clone") for c in calls), calls


def check_own_clone_goes_on(tmp_path: Path, script: Path) -> None:
    calls = run_bootstrap(tmp_path, script, origin=OURS)
    assert calls[-1] == "stopped at the Git Bash step", calls
    assert any(c.endswith(" remote get-url origin") for c in calls), calls


def check_strict_policy_is_lowered_for_the_user_only(
    tmp_path: Path, script: Path
) -> None:
    calls = run_bootstrap(tmp_path, script, origin=OURS, policy="Restricted")
    sets = [c for c in calls if c.startswith("Set-ExecutionPolicy")]
    assert sets == ["Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"], calls
    assert calls[-1] == "stopped at the Git Bash step", calls


def check_open_policy_is_left_alone(tmp_path: Path, script: Path) -> None:
    calls = run_bootstrap(tmp_path, script, origin=OURS, policy="RemoteSigned")
    assert "Get-ExecutionPolicy -Scope CurrentUser" in calls, calls
    assert not [c for c in calls if c.startswith("Set-ExecutionPolicy")], calls


@needs_pwsh
def test_a_stranger_clone_is_never_deployed(tmp_path: Path) -> None:
    check_stranger_clone_is_refused(tmp_path, BOOTSTRAP)


@needs_pwsh
def test_a_clone_of_dotfiles_goes_on_to_git_bash(tmp_path: Path) -> None:
    check_own_clone_goes_on(tmp_path, BOOTSTRAP)


@needs_pwsh
def test_a_strict_policy_is_lowered_to_remotesigned_for_the_user(
    tmp_path: Path,
) -> None:
    check_strict_policy_is_lowered_for_the_user_only(tmp_path, BOOTSTRAP)


@needs_pwsh
def test_an_open_policy_is_left_alone(tmp_path: Path) -> None:
    check_open_policy_is_left_alone(tmp_path, BOOTSTRAP)
