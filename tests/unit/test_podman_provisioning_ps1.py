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
import sys
import uuid
from pathlib import Path

import pytest
from _pwsh import powershell_identity, resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.environ.get("DOTFILES_TEST_PWSH_IMAGE")
PWSH = resolve_pwsh(os.environ) or shutil.which("powershell")
RUN_LABEL = "io.hironow.dotfiles.provisioning-test"
pytestmark = pytest.mark.skipif(
    not IMAGE and not PWSH,
    reason="PowerShell unavailable; select an isolated runtime to require these tests",
)


@pytest.fixture(scope="module", autouse=True)
def report_powershell_runtime(request):
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    line = (
        f"PowerShell provisioning: image {IMAGE}"
        if IMAGE
        else f"PowerShell provisioning: {PWSH} {powershell_identity(PWSH)}"
    )
    if reporter is not None:
        reporter.write_line(line)


# winget exit codes, measured with winget 1.29.380 on Windows 11 (2026-11-11).
NOT_FOUND = -1978335212  # 0x8A150014: no package matches
NO_UPGRADE = -1978335189  # 0x8A15002B: no newer version
INSTALLER_FAILED = -1978335159  # 0x8A150049: the MSI refused (old Podman present)


def _run(
    tmp_path: Path,
    *,
    podman_only: bool = True,
    initial: str | None = None,
    legacy: bool = False,
    cli: str | None = None,
    latest: str = "6.1.4",
    codes: dict[str, int] | None = None,
    uninstall_keeps_key: bool = False,
    machine_running: bool = False,
    install_lands_elsewhere: bool = False,
):
    """Run bootstrap.ps1 against fakes that keep state like the real host.

    `legacy` is the Red Hat installer (RedHat.Podman 5.8.3): its registry
    value, its podman.exe, and its Machine PATH entry. `cli` is the installed
    Podman.CLI version. As measured, Podman.CLI's MSI refuses to install while
    the legacy registry value exists. `initial` is a podman found elsewhere.
    """
    encoded = base64.b64encode((ROOT / "bootstrap.ps1").read_bytes()).decode("ascii")
    settings = base64.b64encode(
        json.dumps(
            {
                "only": podman_only,
                "initial": initial,
                "legacy": legacy,
                "cli": cli,
                "latest": latest,
                "codes": codes or {},
                "uninstallKeepsKey": uninstall_keeps_key,
                "machineRunning": machine_running,
                "installLandsElsewhere": install_lands_elsewhere,
                "notFound": NOT_FOUND,
                "noUpgrade": NO_UPGRADE,
                "installerFailed": INSTALLER_FAILED,
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
$global:S = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SETTINGS__')) | ConvertFrom-Json
$global:LegacyDir = Join-Path (Join-Path $root 'RedHat') 'Podman'
$global:CliDir = Join-Path $root 'Podman'
$global:OtherDir = Join-Path $root 'Other'
$global:MachinePath = [System.Collections.Generic.List[string]]::new()
$global:LegacyKey = [bool]$S.legacy
$global:Cli = $S.cli
$global:Podman = $null
function global:Set-FakePodman([string]$dir, [string]$version) {
    $null = New-Item -ItemType Directory -Force -Path $dir
    $null = New-Item -ItemType File -Force -Path (Join-Path $dir 'podman.exe')
    $global:Podman = [pscustomobject]@{ Source = (Join-Path $dir 'podman.exe'); Version = $version }
}
if ($S.legacy) { Set-FakePodman $LegacyDir '5.8.3'; $MachinePath.Add($LegacyDir + '\') }
elseif ($S.cli) { Set-FakePodman $CliDir $S.cli; $MachinePath.Add($CliDir) }
elseif ($S.initial) { Set-FakePodman $OtherDir $S.initial }
function global:Get-Command {
    [CmdletBinding()]
    param([string]$Name)
    if ($Name -in @('podman', 'podman.exe')) {
        if ($null -ne $global:Podman) { return [pscustomobject]@{ Name = $Name; Source = $global:Podman.Source } }
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
    if ($null -eq $global:Podman) { throw 'UNAVAILABLE fake Podman' }
    'podman version ' + $global:Podman.Version
}
function global:Get-ItemProperty {
    [CmdletBinding()]
    param([string]$LiteralPath, [string]$Name)
    if ($LiteralPath -eq 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Red Hat\Podman') {
        if ($global:LegacyKey) { return [pscustomobject]@{ InstallDir = $global:LegacyDir + '\' } }
        return $null
    }
    if ($LiteralPath -eq 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\Environment') {
        return [pscustomobject]@{ Path = ($global:MachinePath -join ';') }
    }
    throw "UNEXPECTED registry read $LiteralPath"
}
function global:Get-Process {
    [CmdletBinding()]
    param([string[]]$Name)
    if ($global:S.machineRunning) { return [pscustomobject]@{ Name = 'gvproxy' } }
}
function global:Code([string]$verb, [int]$default) {
    $override = $global:S.codes.$verb
    if ($null -ne $override) { return [int]$override }
    return $default
}
function global:winget {
    $a = @($args)
    $global:Calls.Add('winget ' + ($a -join ' '))
    $verb = $a[0]
    $id = $a[[array]::IndexOf($a, '--id') + 1]
    $code = 0
    switch ($verb) {
        'show' { $code = Code 'show' 0 }
        'list' {
            if ($id -eq 'Podman.CLI' -and $global:Cli) { $code = 0 }
            elseif ($id -eq 'RedHat.Podman' -and $global:LegacyKey) { $code = 0 }
            else { $code = $global:S.notFound }
        }
        'uninstall' {
            if ($id -ne 'RedHat.Podman') { throw "UNEXPECTED uninstall $id" }
            $code = Code 'uninstall' 0
            if (-not $global:S.uninstallKeepsKey) {
                $global:LegacyKey = $false
                Remove-Item -LiteralPath (Join-Path $global:LegacyDir 'podman.exe') -Force -ErrorAction SilentlyContinue
                $null = $global:MachinePath.Remove($global:LegacyDir + '\')
                if ($global:Podman -and $global:Podman.Source.StartsWith($global:LegacyDir)) { $global:Podman = $null }
            }
        }
        'install' {
            if ($id -ne 'Podman.CLI') { throw "UNEXPECTED install $id" }
            if ($global:LegacyKey) { $code = $global:S.installerFailed }
            else {
                $code = Code 'install' 0
                if ($code -eq 0) {
                    $global:Cli = $global:S.latest
                    if ($global:S.installLandsElsewhere) { Set-FakePodman $global:OtherDir $global:S.latest }
                    else { Set-FakePodman $global:CliDir $global:S.latest; $global:MachinePath.Add($global:CliDir) }
                }
            }
        }
        'upgrade' {
            if ($id -ne 'Podman.CLI') { throw "UNEXPECTED upgrade $id" }
            if (-not $global:Cli) { $code = $global:S.notFound }
            elseif ($global:Cli -eq $global:S.latest) { $code = Code 'upgrade' $global:S.noUpgrade }
            else {
                $code = Code 'upgrade' 0
                if ($code -eq 0) { $global:Cli = $global:S.latest; Set-FakePodman $global:CliDir $global:S.latest }
            }
        }
        default { throw "UNEXPECTED winget $verb" }
    }
    'fake winget output that must not leak into return values'
    $global:LASTEXITCODE = $code
}
function global:Get-ExecutionPolicy {
    if (-not $global:S.only) {
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
$global:Calls.Clear()
try {
    $source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__'))
    Set-Content -Path $script -Value $source -Encoding UTF8
    Write-Output 'DOTFILES_PS_TARGET_BEGIN'
    try {
        if ($S.only) { & $script -PodmanOnly } else { & $script }
    } catch {
        if ($_.Exception.Message -ne 'EXPECTED normal bootstrap boundary') {
            $global:Calls.Add('error: ' + $_.Exception.Message)
        }
    }
    'DOTFILES_PS_RECEIPT=' + (ConvertTo-Json -InputObject @($global:Calls) -Compress)
    'DOTFILES_PS_STATE=' + (ConvertTo-Json -Compress -InputObject @{
        legacyKey = [bool]$global:LegacyKey
        cli = $global:Cli
        podman = $(if ($global:Podman) { $global:Podman.Version } else { $null })
    })
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
""".replace("__SOURCE__", encoded).replace("__SETTINGS__", settings)
    args = [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
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


def test_bootstrap_runs_under_bypass_like_just_podman_install(tmp_path, monkeypatch):
    # `just podman-install` starts bootstrap.ps1 with -ExecutionPolicy Bypass;
    # a machine policy such as AllSigned must not decide the test either.
    seen = {}

    def record(command, **kwargs):
        seen["command"] = command
        raise RuntimeError("recorded")

    monkeypatch.setattr(sys.modules[__name__], "IMAGE", None)
    monkeypatch.setattr(sys.modules[__name__], "PWSH", "pwsh-under-test")
    monkeypatch.setattr(subprocess, "run", record)
    with pytest.raises(RuntimeError, match="recorded"):
        _run(tmp_path)
    command = seen["command"]
    assert command[command.index("-ExecutionPolicy") + 1] == "Bypass"


def _lines(result: subprocess.CompletedProcess[str], prefix: str):
    assert result.returncode == 0, result.stdout + result.stderr
    found = [
        line.removeprefix(prefix)
        for line in result.stdout.splitlines()
        if line.startswith(prefix)
    ]
    assert len(found) == 1, result.stdout
    return json.loads(found[0])


def _calls(result: subprocess.CompletedProcess[str]) -> list[str]:
    return _lines(result, "DOTFILES_PS_RECEIPT=")


def _state(result: subprocess.CompletedProcess[str]) -> dict:
    return _lines(result, "DOTFILES_PS_STATE=")


def _verbs(calls: list[str]) -> list[str]:
    """Each winget call as `<verb> <id>`; other calls as they are."""
    out = []
    for call in calls:
        args = call.split()
        if args[0] == "winget":
            out.append(f"{args[1]} {args[args.index('--id') + 1]}")
        else:
            out.append(call)
    return out


def _winget(calls: list[str], verb: str) -> list[str]:
    (call,) = [c for c in calls if c.startswith(f"winget {verb} ")]
    return call.split()


INSTALL_FLAGS = {
    "--exact",
    "--silent",
    "--disable-interactivity",
    "--accept-package-agreements",
    "--accept-source-agreements",
}


def test_normal_bootstrap_leaves_an_installed_podman_alone(tmp_path: Path):
    # ADR 0039: rerunning the bootstrap on a set-up machine changes nothing.
    calls = _calls(_run(tmp_path, podman_only=False, legacy=True))
    assert calls == ["podman --version", "normal bootstrap boundary"]


def test_normal_bootstrap_installs_a_missing_podman_before_remaining_steps(
    tmp_path: Path,
):
    calls = _calls(_run(tmp_path, podman_only=False))
    assert _verbs(calls) == [
        "show Podman.CLI",
        "list Podman.CLI",
        "install Podman.CLI",
        "podman --version",
        "normal bootstrap boundary",
    ]


def test_missing_podman_installs_podman_cli_for_all_users(tmp_path: Path):
    result = _run(tmp_path)
    calls = _calls(result)
    assert _verbs(calls) == [
        "show Podman.CLI",
        "list Podman.CLI",
        "install Podman.CLI",
        "podman --version",
    ]
    args = _winget(calls, "install")
    assert args[args.index("--source") + 1] == "winget"
    assert args[args.index("--custom") + 1] == "ALLUSERS=1"
    assert INSTALL_FLAGS <= set(args)
    assert "WSLCheckbox=0" not in args
    assert _state(result) == {"legacyKey": False, "cli": "6.1.4", "podman": "6.1.4"}


def test_red_hat_podman_is_removed_before_podman_cli_is_installed(tmp_path: Path):
    # Podman.CLI's MSI refuses to install beside it (measured 2026-11-11).
    result = _run(tmp_path, legacy=True)
    calls = _calls(result)
    assert _verbs(calls) == [
        "show Podman.CLI",
        "uninstall RedHat.Podman",
        "list Podman.CLI",
        "install Podman.CLI",
        "podman --version",
    ]
    assert _state(result) == {"legacyKey": False, "cli": "6.1.4", "podman": "6.1.4"}


def test_a_running_machine_stops_before_anything_is_removed(tmp_path: Path):
    calls = _calls(_run(tmp_path, legacy=True, machine_running=True))
    assert [c for c in calls if c.startswith("winget ")] == [calls[0]]
    assert _verbs(calls)[:1] == ["show Podman.CLI"]
    assert "podman machine stop" in calls[-1]


def test_an_unreachable_source_stops_before_anything_is_removed(tmp_path: Path):
    result = _run(tmp_path, legacy=True, codes={"show": NOT_FOUND})
    calls = _calls(result)
    assert _verbs(calls)[:1] == ["show Podman.CLI"]
    assert calls[-1].startswith("error: ")
    assert _state(result)["legacyKey"] is True


def test_an_uninstall_that_leaves_the_registry_value_stops(tmp_path: Path):
    calls = _calls(_run(tmp_path, legacy=True, uninstall_keeps_key=True))
    assert not any(c.startswith("winget install") for c in calls)
    assert "Add or Remove Programs" in calls[-1]


def test_an_uninstall_that_asks_for_a_restart_but_removed_it_goes_on(tmp_path: Path):
    calls = _calls(_run(tmp_path, legacy=True, codes={"uninstall": 3010}))
    assert "install Podman.CLI" in _verbs(calls)
    assert calls[-1] == "podman --version"


def test_an_installed_podman_cli_is_upgraded(tmp_path: Path):
    result = _run(tmp_path, cli="6.1.3")
    calls = _calls(result)
    assert _verbs(calls) == [
        "show Podman.CLI",
        "list Podman.CLI",
        "upgrade Podman.CLI",
        "podman --version",
    ]
    args = _winget(calls, "upgrade")
    assert args[args.index("--custom") + 1] == "ALLUSERS=1"
    assert INSTALL_FLAGS <= set(args)
    assert _state(result)["podman"] == "6.1.4"


def test_no_newer_podman_cli_is_success(tmp_path: Path):
    # 0x8A15002B, measured for a no-op upgrade (2026-11-11)
    calls = _calls(_run(tmp_path, cli="6.1.4"))
    assert calls[-1] == "podman --version"


def test_a_failed_upgrade_stops(tmp_path: Path):
    calls = _calls(_run(tmp_path, cli="6.1.3", codes={"upgrade": 1603}))
    assert "1603" in calls[-1]


def test_an_install_that_lands_elsewhere_stops(tmp_path: Path):
    calls = _calls(_run(tmp_path, install_lands_elsewhere=True))
    assert calls[-1].startswith("error: ")
    assert "Podman" in calls[-1]


def test_winget_output_is_shown_to_the_operator(tmp_path: Path):
    # The MSI's reason for a refusal is only in winget's text, so it is shown
    # (Out-Host), not discarded; it never mixes into a return value, or the
    # exit-code checks above would fail.
    result = _run(tmp_path, legacy=True)
    assert "fake winget output" in result.stdout.split("DOTFILES_PS_TARGET_BEGIN")[1]
