"""Test the public Windows provisioning switch with fake native commands.

An explicitly selected image runs PowerShell inside a network-disabled Podman
container. This verifies PowerShell behavior, not native Windows installation.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.environ.get("DOTFILES_TEST_PWSH_IMAGE")
PWSH = shutil.which("pwsh") or shutil.which("powershell")
RUN_LABEL = "io.hironow.dotfiles.provisioning-test"
pytestmark = pytest.mark.skipif(
    not IMAGE and not PWSH,
    reason="PowerShell unavailable; select an isolated runtime to require these tests",
)


def _run(
    tmp_path: Path,
    initial_version: str | None = "5.6.2",
    installed_version: str | None = "6.1.4",
    *,
    podman_only: bool = True,
):
    encoded = base64.b64encode((ROOT / "bootstrap.ps1").read_bytes()).decode("ascii")
    settings = base64.b64encode(
        json.dumps(
            {
                "initial": initial_version,
                "installed": installed_version,
                "only": podman_only,
            }
        ).encode("utf-8")
    ).decode("ascii")
    program = r"""
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('dotfiles-test-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $root
$env:ProgramFiles = $root
$env:LOCALAPPDATA = $root
$env:OS = 'Windows_NT'
$script = Join-Path $root 'bootstrap.ps1'
$global:Calls = [System.Collections.Generic.List[string]]::new()
$global:LASTEXITCODE = 0
$settings = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SETTINGS__')) | ConvertFrom-Json
$global:NativeVersion = $settings.initial
$global:InstalledVersion = $settings.installed
$global:NormalMode = -not $settings.only
function global:Get-Command {
    [CmdletBinding()]
    param([string]$Name)
    if ($Name -in @('podman', 'podman.exe')) {
        if ($null -ne $global:NativeVersion) { return [pscustomobject]@{ Name = $Name } }
        return $null
    }
    if ($Name -in @('winget', 'winget.exe')) { return [pscustomobject]@{ Name = $Name } }
    Microsoft.PowerShell.Core\Get-Command -Name $Name -ErrorAction SilentlyContinue
}
function global:podman {
    $Arguments = @($args)
    $global:Calls.Add('podman ' + ($Arguments -join ' '))
    if (($Arguments -join ' ') -ne '--version') { throw 'UNEXPECTED machine operation' }
    $global:LASTEXITCODE = 0
    if ($null -eq $global:NativeVersion) { throw 'UNAVAILABLE fake Podman' }
    'podman version ' + $global:NativeVersion
}
function global:winget {
    $global:Calls.Add('winget ' + ($args -join ' '))
    $global:NativeVersion = $global:InstalledVersion
    $global:LASTEXITCODE = 0
}
function global:Get-ExecutionPolicy {
    if ($global:NormalMode) {
        $global:Calls.Add('normal bootstrap boundary')
        throw 'EXPECTED normal bootstrap boundary'
    }
    throw 'UNEXPECTED execution policy access'
}
function global:Set-ExecutionPolicy { throw 'UNEXPECTED execution policy change' }
function global:Invoke-RestMethod { throw 'UNEXPECTED download' }
function global:Invoke-Expression { throw 'UNEXPECTED bootstrap evaluation' }
function global:git { throw 'UNEXPECTED checkout mutation' }
function global:just { throw 'UNEXPECTED deploy or sync' }
function global:scoop { throw 'UNEXPECTED unrelated provisioning' }
Write-Output 'DOTFILES_PS_FIXTURE_BEGIN'
if ($null -ne $global:NativeVersion) {
    if ((podman --version) -ne ('podman version ' + $global:NativeVersion)) { throw 'BROKEN version fixture' }
}
$global:Calls.Clear()
try {
    $source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__'))
    Set-Content -Path $script -Value $source -Encoding UTF8
    Write-Output 'DOTFILES_PS_TARGET_BEGIN'
    if ($settings.only) {
        & $script -PodmanOnly
    } else {
        try { & $script }
        catch {
            if ($_.Exception.Message -ne 'EXPECTED normal bootstrap boundary') { throw }
        }
    }
    'DOTFILES_PS_RECEIPT=' + (ConvertTo-Json -InputObject @($global:Calls) -Compress)
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
""".replace("__SOURCE__", encoded).replace("__SETTINGS__", settings)
    args = [
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "& ([scriptblock]::Create([Console]::In.ReadToEnd()))",
    ]
    token = uuid.uuid4().hex
    cidfile = tmp_path / "container.id"
    podman = None
    if IMAGE:
        podman = shutil.which("podman")
        assert podman, "explicit container runtime requires Podman (no Docker fallback)"
        command = [
            podman,
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--name",
            f"dotfiles-pwsh-test-{token}",
            "--label",
            f"{RUN_LABEL}={token}",
            "--cidfile",
            str(cidfile),
            "--env",
            "TERM=dumb",
            "--entrypoint",
            "pwsh",
            "-i",
            IMAGE,
            *args,
        ]
    else:
        assert PWSH
        command = [PWSH, *args]
    try:
        return subprocess.run(
            command,
            input=program,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    finally:
        # --rm handles normal exits; timeout cleanup must prove exact ownership.
        ids = []
        if podman:
            if cidfile.is_file():
                ids = [cidfile.read_text(encoding="utf-8").strip()]
            else:
                discovered = subprocess.run(
                    [
                        podman,
                        "ps",
                        "--all",
                        "--no-trunc",
                        "--filter",
                        f"label={RUN_LABEL}={token}",
                        "--format",
                        "{{.ID}}",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                    timeout=15,
                )
                ids = discovered.stdout.splitlines()
                (tmp_path / "discovered-container-ids.json").write_text(
                    json.dumps(ids), encoding="utf-8"
                )
        for cid in ids:
            assert podman
            assert re.fullmatch(r"[0-9a-f]{64}", cid), "invalid recorded container ID"
            inspected = subprocess.run(
                [podman, "container", "inspect", cid],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=15,
            )
            if inspected.returncode == 0:
                info = json.loads(inspected.stdout)[0]
                assert info["Id"] == cid
                assert info["Config"]["Labels"].get(RUN_LABEL) == token
                subprocess.run(
                    [podman, "container", "rm", "--force", cid],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                    timeout=15,
                )


def _calls(result: subprocess.CompletedProcess[str]) -> list[str]:
    assert result.returncode == 0, result.stdout + result.stderr
    receipts = [
        line.removeprefix("DOTFILES_PS_RECEIPT=")
        for line in result.stdout.splitlines()
        if line.startswith("DOTFILES_PS_RECEIPT=")
    ]
    assert len(receipts) == 1, result.stdout
    return json.loads(receipts[0])


def test_normal_windows_bootstrap_provisions_native_cli_before_remaining_steps(
    tmp_path: Path,
):
    assert _calls(_run(tmp_path, podman_only=False)) == [
        "podman --version",
        "normal bootstrap boundary",
    ]


def test_installed_windows_cli_returns_before_bootstrap_side_effects(tmp_path: Path):
    assert _calls(_run(tmp_path)) == ["podman --version"]


def test_old_windows_cli_uses_native_upgrade_and_rechecks_version(tmp_path: Path):
    calls = _calls(_run(tmp_path, initial_version="4.3.1"))
    assert calls[0] == calls[2] == "podman --version"
    assert len(calls) == 3
    args = calls[1].split()
    assert args[:2] == ["winget", "upgrade"]
    assert args[args.index("--id") + 1] == "RedHat.Podman"
    assert args[args.index("--source") + 1] == "winget"
    assert args[args.index("--custom") + 1] == "WSLCheckbox=0"
    assert "--disable-interactivity" in args


def test_missing_windows_cli_uses_only_the_podman_winget_exception(tmp_path: Path):
    calls = _calls(_run(tmp_path, initial_version=None))
    assert len(calls) == 2
    assert calls[1] == "podman --version"
    args = calls[0].split()
    assert args[:2] == ["winget", "install"]
    for key, value in (
        ("--id", "RedHat.Podman"),
        ("--source", "winget"),
        ("--custom", "WSLCheckbox=0"),
    ):
        assert args[args.index(key) + 1] == value
    assert {
        "--exact",
        "--silent",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements",
    } <= set(args)
