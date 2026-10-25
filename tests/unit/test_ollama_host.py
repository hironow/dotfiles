"""Canonical Windows Ollama ownership and fail-closed WSL sharing policy."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import copy
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ollama_host as host


def _windows() -> dict:
    root = r"C:\Users\dev\scoop\apps\ollama-full\0.40.10"
    return {
        "full_dir": root,
        "full_bucket": "extras",
        "duplicates": [],
        "listeners": [
            {"address": "127.0.0.1", "pid": 42, "path": root + r"\ollama.exe"}
        ],
        "python": r"C:\Users\dev\mise\installs\python\3.15.0\python.exe",
        "version": "0.40.10",
        "errors": [],
    }


def _wsl() -> dict:
    return {
        "native": [],
        "services": [],
        "models": False,
        "errors": [],
        "client_managed": True,
        "bridge_managed": True,
        "bridge_active": True,
        "bridge_owned": True,
        "loopback_only": True,
        "version": "0.40.10",
    }


def _has(rows: list, severity: str, name: str) -> bool:
    return any(row[0] == severity and row[1] == name for row in rows)


@pytest.mark.parametrize(
    ("system", "release", "expected"),
    [
        ("win32", "", "windows-full"),
        ("linux", "6.6-microsoft-standard-WSL2", "wsl-client"),
        ("linux", "6.8-generic", None),
        ("darwin", "", None),
    ],
)
def test_platform_policy(system: str, release: str, expected: str | None) -> None:
    assert host.host_policy(system, release) == expected


def test_checker_and_stable_deployment_can_have_different_paths(tmp_path: Path) -> None:
    checker = tmp_path / "checkout.py"
    deployed = tmp_path / "stable.py"
    content = f"#!/usr/bin/python3\n{host.HELPER_MARKER}\nprint('same')\n"
    checker.write_text(content, encoding="utf-8")
    deployed.write_text(content, encoding="utf-8", newline="\n")
    assert host.deployment_matches(deployed, checker)
    deployed.write_text(content + "# altered\n", encoding="utf-8", newline="\n")
    assert not host.deployment_matches(deployed, checker)


def test_canonical_windows_owner_is_healthy() -> None:
    rows = host.windows_findings(_windows())
    assert not any(row[0] != "OK" for row in rows)


@pytest.mark.parametrize(
    "duplicate", ["scoop/ollama", "winget/Ollama.Ollama", "standalone/Ollama"]
)
def test_installs_outside_path_still_violate_policy(duplicate: str) -> None:
    data = _windows()
    data["duplicates"] = [duplicate]
    assert _has(host.windows_findings(data), "ERR", "ollama-install")


@pytest.mark.parametrize(
    "path",
    [
        r"C:\other\ollama.exe",
        r"C:\Users\dev\scoop\apps\ollama-full\0.40.10-evil\ollama.exe",
        "",
    ],
)
def test_healthy_http_is_not_canonical_ownership(path: str) -> None:
    data = _windows()
    data["listeners"][0]["path"] = path
    assert _has(host.windows_findings(data), "ERR", "ollama-owner")
    assert not host.backend_owned(data)


@pytest.mark.parametrize("address", ["0.0.0.0", "::", "172.21.64.1"])
def test_non_loopback_exposure_is_an_error(address: str) -> None:
    data = _windows()
    data["listeners"][0]["address"] = address
    assert _has(host.windows_findings(data), "ERR", "ollama-exposure")
    assert not host.backend_owned(data)


def test_backend_down_cannot_forward_back_into_wsl() -> None:
    data = _windows()
    data["listeners"] = []
    assert not host.backend_owned(data)
    assert _has(host.windows_findings(data), "WARN", "ollama-owner")


def test_missing_full_or_wrong_bucket_is_not_accepted() -> None:
    for key, value in [("full_dir", ""), ("full_bucket", "main")]:
        data = _windows()
        data[key] = value
        assert _has(host.windows_findings(data), "ERR", "ollama-install")
        assert not host.backend_owned(data)


def test_canonical_scoop_shim_launcher_is_not_a_second_backend() -> None:
    data = _windows()
    data["processes"] = [
        {
            "path": r"C:\Users\dev\scoop\shims\ollama.exe",
            "pid": 100,
            "trusted_shim": True,
        }
    ]
    assert host.backend_owned(data)
    data["processes"][0]["trusted_shim"] = False
    assert not host.backend_owned(data)
    data["processes"][0]["trusted_shim"] = True
    data["listeners"].append(
        {
            "path": data["processes"][0]["path"],
            "pid": 100,
            "address": "127.0.0.1",
            "port": 11435,
        }
    )
    assert not host.backend_owned(data)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="exercise the Windows classifier, not a Python reimplementation",
)
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("valid", True),
        ("unsigned", False),
        ("wrong-signer", False),
        ("wrong-path", False),
        ("wrong-name", False),
        ("wrong-port", False),
        ("wildcard", False),
        ("ipv4", False),
        ("link-file", False),
        ("link-parent", False),
        ("inspection-error", False),
        ("signature-error", False),
    ],
)
def test_powershell_forwarder_classifier_is_narrow(mode: str, expected: bool) -> None:
    fixture = r"""
$ErrorActionPreference='Stop'
function Get-Item {
 param([string]$LiteralPath,[string]$ErrorAction)
 if($script:mode -eq 'inspection-error'){throw 'uninspectable'}
 $attributes=32
 if(($script:mode -eq 'link-file' -and $LiteralPath.EndsWith('.exe')) -or ($script:mode -eq 'link-parent' -and -not $LiteralPath.EndsWith('.exe'))){$attributes=1024}
 [pscustomobject]@{FullName=$LiteralPath;Attributes=[IO.FileAttributes]$attributes}
}
function Get-AuthenticodeSignature {
 param([string]$FilePath,[string]$ErrorAction)
 if($script:mode -eq 'signature-error'){throw 'signature unavailable'}
 $status=if($script:mode -eq 'unsigned'){'NotSigned'}else{'Valid'}
 $subject=if($script:mode -eq 'wrong-signer'){'CN=Unrelated, O=Other'}else{'CN=Microsoft Corporation, O=Microsoft Corporation, C=US'}
 [pscustomobject]@{Status=$status;SignerCertificate=[pscustomobject]@{Subject=$subject}}
}
$path=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'WSL\wslrelay.exe'
if($script:mode -eq 'wrong-path'){$path=Join-Path $env:TEMP 'wslrelay.exe'}
if($script:mode -eq 'wrong-name'){$path=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'WSL\wslhost.exe'}
$address=if($script:mode -eq 'wildcard'){'::'}elseif($script:mode -eq 'ipv4'){'127.0.0.1'}else{'::1'}
$port=if($script:mode -eq 'wrong-port'){11435}else{11434}
Test-DotfilesWslForwarder $path $address $port | ConvertTo-Json -Compress
"""
    script = (
        "$env:PSModulePath='C:/nonexistent-powershell7-modules'\n"
        + host.WINDOWS_FORWARDER_CLASSIFIER
        + f"\n$script:mode='{mode}'\n"
        + fixture
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [
            host.powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    )
    assert json.loads(result.stdout) is expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows builtin module isolation")
def test_windows_security_module_ignores_inherited_powershell7_paths() -> None:
    script = (
        "$env:PSModulePath='C:/nonexistent-powershell7-modules'\n"
        + host.WINDOWS_FORWARDER_CLASSIFIER
        + "\n(Get-AuthenticodeSignature -FilePath (Join-Path $PSHOME 'powershell.exe')).Status -eq 'Valid' | ConvertTo-Json"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [
            host.powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    )
    assert json.loads(result.stdout) is True


windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="exercise the Windows PowerShell code, not a Python reimplementation",
)


def _powershell(script: str) -> str:
    """Runs Windows PowerShell 5.1 the way the probe does; returns stdout."""
    result = host.run_powershell(script, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


# A generic serve configuration with the shapes a GPU box carries: an HTTPS
# web proxy on 443, unrelated TCP forwards, and the declared 11434 forward.
SERVE: dict[str, Any] = {
    "TCP": {
        "443": {"HTTPS": True},
        "8775": {"TCPForward": "localhost:8775"},
        "11434": {"TCPForward": "localhost:11434"},
        "18021": {"TCPForward": "localhost:18020"},
    },
    "Web": {
        "node.example.ts.net:443": {
            "Handlers": {"/": {"Proxy": "http://127.0.0.1:8188"}}
        }
    },
}


def _serve(**changes: Any) -> dict[str, Any]:
    config: dict[str, Any] = copy.deepcopy(SERVE)
    for key, value in changes.items():
        if key == "forward":
            config["TCP"]["11434"] = value
        elif key == "tcp":
            config["TCP"].update(value)
        elif key == "web":
            config["Web"].update(value)
        else:
            config[key] = value
    return config


@windows_only
@pytest.mark.parametrize(
    "config,v6_taken,accepted",
    [
        pytest.param(_serve(), False, True, id="the-declared-shape"),
        pytest.param(
            _serve(forward={"TCPForward": "127.0.0.1:11434"}),
            True,
            True,
            id="ipv4-target",
        ),
        pytest.param(_serve(), True, False, id="localhost-with-a-v6-listener"),
        pytest.param(
            _serve(AllowFunnel={"node.example.ts.net:443": True}),
            False,
            False,
            id="funnel-on-443",
        ),
        pytest.param(
            _serve(AllowFunnel={"node.example.ts.net:443": False}),
            False,
            True,
            id="funnel-off",
        ),
        pytest.param(
            _serve(
                Foreground={"s": {"AllowFunnel": {"node.example.ts.net:8443": True}}}
            ),
            False,
            False,
            id="funnel-in-a-foreground-session",
        ),
        pytest.param(
            _serve(
                Foreground={"s": {"TCP": {"11434": {"TCPForward": "localhost:9999"}}}}
            ),
            False,
            False,
            id="foreground-takes-11434",
        ),
        pytest.param(
            _serve(forward={"TCPForward": "localhost:8080"}),
            False,
            False,
            id="other-target",
        ),
        pytest.param(
            _serve(forward={"TCPForward": "0.0.0.0:11434"}),
            False,
            False,
            id="wildcard-target",
        ),
        pytest.param(_serve(forward={"HTTPS": True}), False, False, id="web-not-tcp"),
        pytest.param(
            _serve(
                forward={"TCPForward": "localhost:11434", "TerminateTLS": "n.example"}
            ),
            False,
            False,
            id="tls-terminated",
        ),
        pytest.param(
            _serve(forward={"TCPForward": "localhost:11434", "ProxyProtocol": 1}),
            False,
            False,
            id="proxy-protocol",
        ),
        pytest.param(
            _serve(tcp={"18000": {"TCPForward": "localhost:11434"}}),
            False,
            False,
            id="second-forward-to-11434",
        ),
        pytest.param(
            _serve(
                web={
                    "n.example.ts.net:8443": {
                        "Handlers": {"/": {"Proxy": "http://127.0.0.1:11434"}}
                    }
                }
            ),
            False,
            False,
            id="web-proxy-to-11434",
        ),
        pytest.param(
            _serve(
                web={"n.example.ts.net:8443": {"Handlers": {"/": {"Proxy": "11434"}}}}
            ),
            False,
            False,
            id="bare-port-proxy-to-11434",
        ),
        pytest.param(
            _serve(web={"n.example.ts.net:11434": {"Handlers": {"/": {"Text": "hi"}}}}),
            False,
            False,
            id="web-site-on-11434",
        ),
        pytest.param(
            _serve(
                Services={
                    "svc:x": {"TCP": {"11434": {"TCPForward": "localhost:11434"}}}
                }
            ),
            False,
            False,
            id="service-takes-11434",
        ),
        pytest.param(
            _serve(Services={"svc:x": {"Tun": True}}), False, False, id="tun-service"
        ),
        pytest.param(
            {"TCP": {"8775": {"TCPForward": "localhost:8775"}}},
            False,
            False,
            id="no-forward",
        ),
        pytest.param({}, False, False, id="empty"),
    ],
)
def test_powershell_serve_config_rules(
    config: dict, v6_taken: bool, accepted: bool
) -> None:
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + "\n$config=@'\n"
        + json.dumps(config)
        + "\n'@|ConvertFrom-Json\n"
        + f"@{{reason=[string](Test-DotfilesServeConfig $config ${str(v6_taken).lower()})}}|ConvertTo-Json -Compress"
    )
    reason = json.loads(_powershell(script))["reason"]
    assert (reason == "") is accepted, reason


@windows_only
@pytest.mark.parametrize(
    "address,nodes,accepted",
    [
        ("100.64.12.34", ["100.64.12.34", "fd7a:115c:a1e0::5678"], True),
        ("fd7a:115c:a1e0::5678", ["100.64.12.34", "fd7a:115c:a1e0::5678"], True),
        ("fd7a:115c:a1e0:0:0:0:0:5678", ["fd7a:115c:a1e0::5678"], True),
        ("100.64.12.35", ["100.64.12.34"], False),
        ("192.168.1.20", ["192.168.1.20"], False),
        ("100.128.0.1", ["100.128.0.1"], False),
        ("fd7a:115c:a1e1::1", ["fd7a:115c:a1e1::1"], False),
        ("0.0.0.0", ["0.0.0.0"], False),
        ("not-an-address", ["100.64.12.34"], False),
    ],
)
def test_powershell_tailnet_address_rules(
    address: str, nodes: list[str], accepted: bool
) -> None:
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + f"\nTest-DotfilesTailnetAddress '{address}' @({','.join(repr(n) for n in nodes)})|ConvertTo-Json"
    )
    assert json.loads(_powershell(script)) is accepted


# The service process (pid 70) and its tailscaled child (pid 100), as
# Win32_Process reports them; a normal user cannot see their paths.
LINEAGE = r"""
$facts=@{
  Service=@{State='Running';ProcessId=70}
  Processes=@{
    70=@{ParentProcessId=4;Name='tailscaled.exe';CreationDate=[datetime]'2026-01-01T00:00:00'}
    100=@{ParentProcessId=70;Name='tailscaled.exe';CreationDate=[datetime]'2026-01-01T00:00:01'}
  }
}
"""


@windows_only
@pytest.mark.parametrize(
    "change,owner,accepted",
    [
        ("", 100, True),
        ("", 70, True),
        ("$facts.Service.State='Stopped'", 100, False),
        ("$facts.Service.ProcessId=0", 0, False),
        ("$facts.Processes[100].ParentProcessId=71", 100, False),
        ("$facts.Processes[100].Name='other.exe'", 100, False),
        ("$facts.Processes[70].CreationDate=[datetime]'2026-01-02'", 100, False),
        ("$facts.Processes[100].CreationDate=$null", 100, False),
        ("", 999, False),
    ],
)
def test_powershell_tailnet_lineage_rules(
    change: str, owner: int, accepted: bool
) -> None:
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + LINEAGE
        + change
        + f"\nTest-DotfilesTailnetLineage $facts {owner}|ConvertTo-Json"
    )
    assert json.loads(_powershell(script)) is accepted


@windows_only
@pytest.mark.parametrize(
    "change,port,accepted",
    [
        ("", 11434, True),
        ("$facts.Declared=$false", 11434, False),
        ("$facts.Error='could not inspect'", 11434, False),
        ("", 11435, False),
        ("$facts.ServiceBinaryTrusted=$false", 11434, False),
        ("$facts.NodeAddresses=@('100.64.99.99')", 11434, False),
        ("$facts.Serve=$null", 11434, False),
    ],
)
def test_powershell_tailnet_forward_needs_every_condition(
    change: str, port: int, accepted: bool
) -> None:
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + LINEAGE
        + "\n$facts.Declared=$true;$facts.Error='';$facts.ServiceBinaryTrusted=$true"
        + "\n$facts.NodeAddresses=@('100.64.12.34');$facts.LoopbackV6Taken=$false"
        + "\n$facts.Serve=@'\n"
        + json.dumps(SERVE)
        + "\n'@|ConvertFrom-Json\n"
        + change
        + f"\n@{{reason=[string](Test-DotfilesTailnetForward $facts '100.64.12.34' {port} 100)}}|ConvertTo-Json -Compress"
    )
    reason = json.loads(_powershell(script))["reason"]
    assert (reason == "") is accepted, reason


@windows_only
@pytest.mark.parametrize(
    "content,declared",
    [("11434\r\n", True), ("11434", True), ("11435\n", False), (None, False)],
)
def test_powershell_tailnet_declaration_is_one_exact_line(
    tmp_path: Path, content: str | None, declared: bool
) -> None:
    if content is not None:
        (tmp_path / ".config/dotfiles").mkdir(parents=True)
        (tmp_path / ".config/dotfiles/ollama-tailnet-forward").write_text(
            content, encoding="utf-8"
        )
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + host.WINDOWS_PROBE_FUNCTIONS
        + f"\n$env:USERPROFILE='{tmp_path}'\nRead-DotfilesTailnetDeclaration|ConvertTo-Json"
    )
    assert json.loads(_powershell(script)) is declared


# Stand-ins for what the facts collector reads: the service, the processes,
# the signature check and the Tailscale CLI. $script:* switches change them.
FACT_STUBS = r"""
$ErrorActionPreference='Stop'
$script:declared=$true;$script:serviceCalls=0;$script:cliCalls=0;$script:cliFails=$false
$script:servicePids=@(70);$script:pathName='"C:\Program Files\Tailscale\tailscaled.exe"'
$script:serve='{"TCP":{"11434":{"TCPForward":"localhost:11434"}}}'
function Read-DotfilesTailnetDeclaration{$script:declared}
function Test-DotfilesSignedBinary{param($Path,$Organization) $true}
function Invoke-DotfilesTailscale{
  param([string[]]$Arguments)
  $script:cliCalls++
  if($script:cliFails){throw 'tailscale failed'}
  switch($Arguments -join ' '){'ip -4'{'100.64.12.34'} 'ip -6'{'fd7a:115c:a1e0::5678'} 'serve status --json'{$script:serve}}
}
function Get-CimInstance{
  param([string]$ClassName,[string]$Filter,$ErrorAction)
  if($ClassName -eq 'Win32_Service'){
    $index=[Math]::Min($script:serviceCalls,$script:servicePids.Count-1);$script:serviceCalls++
    return [pscustomobject]@{Name='Tailscale';State='Running';ProcessId=$script:servicePids[$index];PathName=$script:pathName}
  }
  if($Filter -like "*tailscaled.exe*"){return @(
    [pscustomobject]@{ProcessId=70;ParentProcessId=4;Name='tailscaled.exe';CreationDate=[datetime]'2026-01-01T00:00:00'},
    [pscustomobject]@{ProcessId=100;ParentProcessId=70;Name='tailscaled.exe';CreationDate=[datetime]'2026-01-01T00:00:01'})}
  return @([pscustomobject]@{ProcessId=42;Name='ollama.exe';CommandLine='"C:\fake\scoop\apps\ollama-full\current\ollama.exe" serve';ExecutablePath='C:\fake\scoop\apps\ollama-full\0.40.10\ollama.exe'})
}
"""


@windows_only
@pytest.mark.parametrize(
    "change,expect",
    [
        ("", "trusted"),
        ("$script:declared=$false", "undeclared"),
        ("$script:pathName='C:\\Temp\\tailscaled.exe'", "untrusted"),
        ("$script:cliFails=$true", "error"),
    ],
)
def test_powershell_tailnet_facts_collector(change: str, expect: str) -> None:
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + host.WINDOWS_PROBE_FUNCTIONS
        + FACT_STUBS
        + change
        + "\n$facts=Get-DotfilesTailnetFacts $false"
        + "\n@{declared=[bool]$facts.Declared;error=[string]$facts.Error;trusted=[bool]$facts.ServiceBinaryTrusted"
        + ";addresses=@($facts.NodeAddresses);child=$(if($facts.Processes){[int]$facts.Processes[100].ParentProcessId}else{0});cli=$script:cliCalls"
        + ";confirmed=(Confirm-DotfilesTailnetFacts $facts)}|ConvertTo-Json -Compress"
    )
    result = json.loads(_powershell(script))
    if expect == "undeclared":
        assert result["declared"] is False and result["cli"] == 0
        return
    assert result["declared"] is True
    if expect == "error":
        assert result["error"]
        return
    assert result["error"] == ""
    assert result["addresses"] == ["100.64.12.34", "fd7a:115c:a1e0::5678"]
    assert result["child"] == 70
    assert result["confirmed"] is True
    assert result["trusted"] is (expect == "trusted")


# The probe body around the stubs: one canonical backend on 127.0.0.1 and
# tailscaled's child on both tailnet addresses.
PROBE_STUBS = (
    FACT_STUBS
    + r"""
$env:SCOOP='C:\fake\scoop';$script:versionCalls=0;$script:netError=$false
function Get-DotfilesBackendVersion{$script:versionCalls++;'0.40.10'}
function Test-Path{param([string]$Path) $Path -in @('C:\fake\scoop\apps\ollama-full\current','C:\fake\scoop\apps\ollama-full\current\scoop-install.json')}
function Get-Item{param([string]$Path,[string]$LiteralPath,$ErrorAction) [pscustomobject]@{Target='C:\fake\scoop\apps\ollama-full\0.40.10';FullName=$Path;Attributes=[IO.FileAttributes]::Directory}}
function Get-Content{param([string]$Path,[switch]$Raw) '{"bucket":"extras"}'}
function Get-ChildItem{param($Path,[switch]$Directory,$ErrorAction) @()}
function Get-ItemProperty{param($Path,$ErrorAction) @()}
function Get-NetTCPConnection{param($State,$ErrorAction) @(
  [pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=11434;OwningProcess=42},
  [pscustomobject]@{LocalAddress='100.64.12.34';LocalPort=11434;OwningProcess=100},
  [pscustomobject]@{LocalAddress='fd7a:115c:a1e0::5678';LocalPort=11434;OwningProcess=100})
  # Like the real cmdlet, the caller's -ErrorAction decides whether this stops it.
  if($script:netError){Write-Error 'the listener table was cut short' -ErrorAction $ErrorAction}}
function Get-Process{param($Id,$ErrorAction) [pscustomobject]@{Path=$(if($Id -eq 42){'C:\fake\scoop\apps\ollama-full\0.40.10\ollama.exe'}else{$null})}}
"""
)


@windows_only
@pytest.mark.parametrize(
    "change,forwards,refused,versions",
    [
        ("", 2, "", 1),
        (
            '$script:serve=\'{"TCP":{"11434":{"TCPForward":"localhost:11434"}},"AllowFunnel":{"n:443":true}}\'',
            0,
            "Funnel is on",
            0,
        ),
        ("$script:declared=$false", 0, "", 0),
        ("$script:servicePids=@(70,71)", 0, "changed during the check", 0),
        ("$script:netError=$true", 0, "", 0),
    ],
)
def test_windows_probe_wires_the_tailnet_forward(
    change: str, forwards: int, refused: str, versions: int
) -> None:
    script = (
        host.WINDOWS_FORWARDER_CLASSIFIER
        + host.WINDOWS_TAILNET_CLASSIFIER
        + host.WINDOWS_PROBE_FUNCTIONS
        + PROBE_STUBS
        + change
        + host.WINDOWS_PROBE_BODY
        + '\n"VERSION_CALLS=$script:versionCalls"'
    )
    lines = _powershell(script).strip().splitlines()
    data = json.loads(lines[0].lstrip("\ufeff"))
    assert lines[1] == f"VERSION_CALLS={versions}"
    assert (
        sum(row.get("tailnet_forward") is True for row in data["listeners"]) == forwards
    )
    reasons = [refusal["reason"] for refusal in data.get("tailnet_refusals", [])]
    if refused:
        assert len(reasons) == 2 and all(refused in reason for reason in reasons), (
            reasons
        )
    else:
        assert reasons == []
    assert host.backend_owned(data) is (forwards == 2)


def test_signed_windows_ipv6_forwarder_is_not_a_second_ollama() -> None:
    data = _windows()
    data["listeners"].append(
        {
            "address": "::1",
            "port": 11434,
            "pid": 99,
            "path": r"C:\Program Files\WSL\wslrelay.exe",
            "windows_forwarder": True,
        }
    )
    assert host.backend_owned(data)
    assert not _has(host.windows_findings(data), "ERR", "ollama-owner")


def test_healthy_ipv6_backend_cannot_authorize_a_forwarded_ipv4_target() -> None:
    data = _windows()
    data["listeners"][0]["address"] = "::1"
    data["listeners"].append(
        {
            "address": "127.0.0.1",
            "port": 11434,
            "pid": 99,
            "path": r"C:\Program Files\WSL\wslrelay.exe",
            "windows_forwarder": True,
        }
    )
    assert not host.backend_owned(data)


def test_ipv6_only_backend_does_not_own_the_fixed_ipv4_transport_target() -> None:
    data = _windows()
    data["listeners"][0]["address"] = "::1"
    assert not host.backend_owned(data)


def test_unsigned_or_exposed_forwarder_is_not_exempted() -> None:
    for address, trusted in [("::1", False), ("::", True)]:
        data = _windows()
        data["listeners"].append(
            {
                "address": address,
                "port": 11434,
                "pid": 99,
                "path": r"C:\Program Files\WSL\wslrelay.exe",
                "windows_forwarder": trusted,
            }
        )
        assert not host.backend_owned(data)


def _tailnet_listeners(verified: bool, port: int = 11434) -> list[dict]:
    # tailscaled's own listeners on the machine's tailnet addresses; the probe
    # cannot see a service child's path without elevation.
    return [
        {"address": address, "port": port, "pid": 7, "path": None}
        | ({"tailnet_forward": True} if verified else {})
        for address in ("100.64.12.34", "fd7a:115c:a1e0::5678")
    ]


def test_declared_tailnet_forward_is_neither_a_backend_nor_an_exposure() -> None:
    data = _windows()
    data["listeners"] += _tailnet_listeners(verified=True)
    rows = host.windows_findings(data)
    assert _has(rows, "OK", "ollama-owner")
    assert _has(rows, "OK", "ollama-exposure")
    assert _has(rows, "OK", "ollama-tailnet-forward")
    assert host.backend_owned(data)


def test_unverified_tailnet_listener_stays_a_second_owner_and_an_exposure() -> None:
    data = _windows()
    data["listeners"] += _tailnet_listeners(verified=False)
    rows = host.windows_findings(data)
    assert _has(rows, "ERR", "ollama-owner")
    assert _has(rows, "ERR", "ollama-exposure")
    assert not any(row[1] == "ollama-tailnet-forward" for row in rows)
    assert not host.backend_owned(data)


def test_tailnet_flag_exempts_only_port_11434() -> None:
    data = _windows()
    data["listeners"] += _tailnet_listeners(verified=True, port=11435)
    assert _has(host.windows_findings(data), "ERR", "ollama-owner")
    assert not host.backend_owned(data)


def test_a_refused_declared_forward_is_an_error_with_its_reason() -> None:
    data = _windows()
    data["listeners"] += _tailnet_listeners(verified=False)
    data["tailnet_refusals"] = [{"address": "100.64.12.34", "reason": "Funnel is on"}]
    rows = host.windows_findings(data)
    assert any(
        row[0] == "ERR"
        and row[1] == "ollama-tailnet-forward"
        and "Funnel is on" in row[2]
        for row in rows
    )
    assert not host.backend_owned(data)


def test_additional_serving_backend_is_rejected() -> None:
    data = _windows()
    data["listeners"].append(
        {"address": "::1", "pid": 43, "path": data["full_dir"] + r"\ollama.exe"}
    )
    assert _has(host.windows_findings(data), "ERR", "ollama-owner")
    assert not host.backend_owned(data)


def test_uninspected_is_never_healthy() -> None:
    data = _windows()
    data["errors"] = ["stopped distribution: Ubuntu"]
    assert _has(host.windows_findings(data), "WARN", "ollama-inspection")


@pytest.mark.parametrize(
    "key,value,name",
    [
        ("native", ["/usr/local/bin/ollama"], "ollama-wsl-native"),
        ("services", ["system:ollama.service:enabled:inactive"], "ollama-wsl-native"),
        ("models", True, "ollama-wsl-models"),
        ("bridge_owned", False, "ollama-bridge"),
        ("bridge_managed", False, "ollama-bridge"),
        ("loopback_only", False, "ollama-exposure"),
        ("conflicting_config", True, "ollama-exposure"),
    ],
)
def test_wsl_violations_are_visible(key: str, value: object, name: str) -> None:
    data = _wsl()
    data[key] = value
    assert _has(host.wsl_findings(data), "ERR", name)


def test_wsl_bridge_version_must_match_canonical_backend() -> None:
    data = _wsl()
    data["version"] = "different"
    assert _has(
        host.wsl_findings(data, windows_version="0.40.10"), "ERR", "ollama-bridge"
    )


def test_backend_outage_is_warned_but_identity_failure_stays_err() -> None:
    data = _wsl()
    data["version"] = ""
    assert _has(host.wsl_findings(data, windows_version=""), "WARN", "ollama-bridge")
    data["bridge_active"] = False
    assert _has(host.wsl_findings(data, windows_version=""), "ERR", "ollama-bridge")


def test_wsl_kernel_container_is_never_a_wsl_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert (
        host.host_policy("linux", "6.6-microsoft-standard-WSL2", container=True) is None
    )
    assert (
        host.host_policy("linux", "6.6-microsoft-standard-WSL2", container=False)
        == "wsl-client"
    )
    sentinels = (tmp_path / "dockerenv", tmp_path / "containerenv")
    monkeypatch.setattr(host, "_CONTAINER_SENTINELS", sentinels)
    monkeypatch.setattr(host.sys, "platform", "linux")
    monkeypatch.setattr(host.platform, "release", lambda: "6.6-microsoft-standard-WSL2")
    assert host.host_policy() == "wsl-client"
    sentinels[0].write_text("", encoding="utf-8")
    assert host.host_policy() is None


def test_missing_transport_and_invalid_version_fail_closed() -> None:
    data = _windows()
    data["python"] = ""
    assert _has(host.windows_findings(data), "WARN", "ollama-transport")
    assert host.backend_owned(data)  # Backend ownership is independent of transport.
    data = _windows()
    data["version"] = {"not": "a version"}
    assert not host.backend_owned(data)


@pytest.mark.parametrize(
    "args",
    [
        ["serve"],
        ["launch"],
        ["--verbose", "serve"],
        ["future-command"],
        ["--host=remote", "list"],
    ],
)
def test_client_refuses_daemon_menu_and_unknown_entrypoints(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(
        host,
        "windows_snapshot",
        lambda: pytest.fail("must reject before probing/launch"),
    )
    with pytest.raises(RuntimeError):
        host.client_command(args)


def test_managed_client_accepts_the_ls_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(host, "interop_environment", lambda: {"WSLENV": ""})
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(host.subprocess, "run", run)
    assert host.client_command(["ls"]) == 0
    assert calls[0][0].endswith("ollama.exe")
    assert calls[0][1:] == ["ls"]


def test_client_preserves_args_and_wslenv_but_pins_windows_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(
        host,
        "interop_environment",
        lambda: {"WSLENV": "KEEP/p:OLLAMA_HOST/p:OTHER/u", "OLLAMA_HOST": "remote"},
    )
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(host.subprocess, "run", run)
    args = ["run", "a-model", "a quote ' and space; $(not-a-shell)"]
    assert host.client_command(args) == 0
    command, kwargs = calls[0]
    assert command[1:] == args
    assert command[0].endswith("ollama.exe")
    assert kwargs["env"]["OLLAMA_HOST"] == "http://127.0.0.1:11434"
    assert kwargs["env"]["WSLENV"] == "KEEP/p:OTHER/u:OLLAMA_HOST"


def test_client_backend_down_never_autostarts_a_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _windows()
    data["listeners"] = []
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", lambda: data)
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("unexpected replacement/CLI launch"),
    )
    with pytest.raises(RuntimeError, match="no daemon or native fallback"):
        host.client_command(["list"])


def test_stable_client_install_is_idempotent_and_preserves_user_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(host.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(host, "DURABLE_PYTHON", sys.executable)
    host.install_client_files()
    helper = host.deployment_source()
    shim = tmp_path / ".local/bin/ollama"
    assert host.deployment_matches(helper, host.SOURCE)
    assert host.managed_cli(shim, helper)
    unit = tmp_path / ".config/systemd/user" / host.UNIT
    assert host.managed_unit(unit.read_text(encoding="utf-8"), str(helper))
    first = helper.read_bytes(), shim.read_bytes(), unit.read_bytes()
    host.install_client_files()
    assert first == (helper.read_bytes(), shim.read_bytes(), unit.read_bytes())
    shim.write_text("# user changed this", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing"):
        host.install_client_files()
    assert shim.read_text(encoding="utf-8") == "# user changed this"


def test_client_files_precede_backend_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    order = []
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "install_client_files", lambda: order.append("files"))

    def unavailable():
        assert order == ["files"]
        raise RuntimeError("interop unavailable")

    monkeypatch.setattr(host, "windows_snapshot", unavailable)
    with pytest.raises(RuntimeError, match="interop unavailable"):
        host.setup()


def test_owned_write_refuses_unrelated_files_and_updates_matching_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "owned"
    path.write_text("user-owned", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing"):
        host._write_owned(path, "managed", None, 0o600)
    assert path.read_text(encoding="utf-8") == "user-owned"
    previous = host._source_hash(path)
    host._write_owned(path, "managed", previous, 0o600)
    assert path.read_text(encoding="utf-8") == "managed"


def test_probe_errors_fail_closed() -> None:
    data = _windows()
    data["errors"] = ["could not inspect listeners"]
    assert not host.backend_owned(data)


def test_systemd_unit_has_fixed_loopback_transport_and_managed_identity() -> None:
    unit = host.bridge_unit(
        "/usr/bin/python3", "/home/user/dotfiles/scripts/ollama_host.py"
    )
    assert host.UNIT_MARKER in unit
    assert "--serve" in unit
    assert "Restart=on-failure" in unit
    assert "ollama serve" not in unit
    assert "WSL_INTEROP=" not in unit  # Session-specific sockets must not be pinned.


def test_managed_unit_rejects_extra_commands_and_wrong_source() -> None:
    source = "/home/user/dotfiles/scripts/ollama_host.py"
    unit = host.bridge_unit("/usr/bin/python3", source)
    assert host.managed_unit(unit, source)
    assert not host.managed_unit(unit + "ExecStartPre=touch /tmp/side-effect\n", source)
    assert not host.managed_unit(unit, "/other/source.py")


@pytest.mark.parametrize(
    "address,trusted,allowed",
    [
        (None, False, True),
        ("::1", True, True),
        ("::1", False, False),
        ("127.0.0.1", True, False),
        ("::", True, False),
    ],
)
def test_windows_startup_distinguishes_forwarder_from_backend(
    monkeypatch: pytest.MonkeyPatch, address: str | None, trusted: bool, allowed: bool
) -> None:
    data = _windows()
    data["version"] = ""
    data["listeners"] = (
        []
        if address is None
        else [
            {
                "address": address,
                "port": 11434,
                "pid": 99,
                "path": r"C:\Program Files\WSL\wslrelay.exe",
                "windows_forwarder": trusted,
            }
        ]
    )
    monkeypatch.setattr(host, "host_policy", lambda: "windows-full")
    monkeypatch.setattr(host, "windows_snapshot", lambda: data)
    calls = []
    monkeypatch.setattr(
        host.subprocess, "Popen", lambda args, **kwargs: calls.append(args)
    )
    if allowed:
        host.setup()
        assert calls == [[str(Path(data["full_dir"]) / "ollama app.exe")]]
    else:
        with pytest.raises(RuntimeError, match="violations"):
            host.setup()
        assert not calls


def test_windows_startup_does_not_launch_another_healthy_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "windows-full")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    calls = []
    monkeypatch.setattr(
        host.subprocess, "Popen", lambda *args, **kwargs: calls.append(args)
    )
    host.setup()
    assert not calls


def test_non_windows_non_wsl_setup_never_probes_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: None)
    monkeypatch.setattr(
        host, "windows_snapshot", lambda: pytest.fail("unexpected Windows probe")
    )
    host.setup()


def test_no_arbitrary_windows_transport_target() -> None:
    command = host.transport_command("/mnt/c/python.exe")
    assert command[-2:] == ["127.0.0.1", "11434"]
    assert all(flag in command for flag in ("-I", "-S", "-B", "-u"))
    compile(host.WINDOWS_STREAM, "<fixed-windows-transport>", "exec")


@pytest.mark.skipif(sys.platform != "win32", reason="the byte adapter runs in Windows")
def test_fixed_windows_code_refuses_noncanonical_target_without_connecting() -> None:
    command = host.transport_command(sys.executable)
    command[-1] = "9"
    result = subprocess.run(command, capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    assert result.stdout == b""


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows byte adapter timeout semantics"
)
def test_receive_timeout_also_applies_during_active_upload() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received = []

    def consume_without_response():
        try:
            connection, _address = listener.accept()
            with connection:
                while data := connection.recv(1024):
                    received.append(data)
        except OSError:
            pass

    server = threading.Thread(target=consume_without_response, daemon=True)
    server.start()
    command = host.transport_command(sys.executable)
    command[-1] = str(port)
    command[-3] = (
        command[-3]
        .replace("11434", str(port))
        .replace("backend.settimeout(300)", "backend.settimeout(0.2)")
    )
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    input_pipe = process.stdin
    assert input_pipe is not None

    def upload():
        try:
            for _ in range(100):
                input_pipe.write(b"x")
                input_pipe.flush()
                time.sleep(0.02)
        except (OSError, ValueError):
            pass

    sender = threading.Thread(target=upload, daemon=True)
    sender.start()
    try:
        assert process.wait(timeout=5) != 0
        assert received, "the upload must have started before receive timeout"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        sender.join(timeout=2)
        process.communicate(timeout=5)
        listener.close()
        server.join(timeout=2)


def test_findings_do_not_mutate_input() -> None:
    data = _windows()
    original = copy.deepcopy(data)
    host.windows_findings(data)
    assert data == original


def test_conflicting_effective_host_configuration_is_an_error() -> None:
    data = _windows()
    data["conflicting_config"] = True
    assert _has(host.windows_findings(data), "ERR", "ollama-exposure")
    assert not host.backend_owned(data)


def test_port_conflict_does_not_remove_an_existing_bridge_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state.json"
    state.write_text('{"pid":123}', encoding="utf-8")
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "_state_path", lambda: state)

    async def conflict(*args, **kwargs):
        raise OSError("port occupied")

    monkeypatch.setattr(host.asyncio, "start_server", conflict)
    with pytest.raises(OSError, match="port occupied"):
        asyncio.run(host.serve())
    assert json.loads(state.read_text(encoding="utf-8"))["pid"] == 123


@pytest.mark.parametrize("backend", ["up", "down"])
def test_opaque_relay_streaming_eof_and_backend_down(
    backend: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _windows()
    if backend == "down":
        data["listeners"] = []
    monkeypatch.setattr(host, "windows_snapshot", lambda: data)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    original_spawn = asyncio.create_subprocess_exec
    children = []

    async def spawn(*args, **kwargs):
        assert list(args)[-2:] == ["127.0.0.1", "11434"]
        process = await original_spawn(
            sys.executable,
            "-u",
            "-c",
            "import sys\nwhile data := sys.stdin.buffer.read1(32768):\n sys.stdout.buffer.write(data); sys.stdout.buffer.flush()\n",
            **kwargs,
        )
        children.append(process)
        return process

    monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)

    async def exercise():
        done = asyncio.Event()

        async def handle(reader, writer):
            try:
                await host._relay(reader, writer, asyncio.Semaphore(1))
            finally:
                done.set()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.sockets[0].getsockname()[1]
            )
            writer.write(b"first")
            await writer.drain()
            if backend == "up":
                # Incremental response must arrive BEFORE stdin EOF/full body.
                assert await asyncio.wait_for(reader.readexactly(5), 5) == b"first"
                payload = bytes(range(256)) * 8192

                async def receive():
                    return await reader.readexactly(len(payload))

                incoming = asyncio.create_task(receive())
                writer.write(payload)
                await writer.drain()
                assert await asyncio.wait_for(incoming, 10) == payload
            else:
                # Linux may reset a refused connection with unread request
                # bytes; both EOF and reset are valid fail-closed outcomes.
                with contextlib.suppress(ConnectionResetError):
                    assert await asyncio.wait_for(reader.read(), 5) == b""
            writer.close()
            with contextlib.suppress(ConnectionResetError):
                await writer.wait_closed()
            await asyncio.wait_for(done.wait(), 10)
        finally:
            server.close()
            await server.wait_closed()
        assert all(child.returncode is not None for child in children)
        assert len(children) == (1 if backend == "up" else 0)

    asyncio.run(exercise())


def test_client_reset_reaps_a_helper_blocked_without_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    original_spawn = asyncio.create_subprocess_exec
    children = []

    async def exercise():
        started = asyncio.Event()
        done = asyncio.Event()
        slots = asyncio.Semaphore(1)

        async def spawn(*args, **kwargs):
            process = await original_spawn(
                sys.executable, "-u", "-c", "import time; time.sleep(300)", **kwargs
            )
            children.append(process)
            started.set()
            return process

        async def handle(reader, writer):
            try:
                await host._relay(reader, writer, slots)
            finally:
                done.set()

        monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        client = socket.socket()
        try:
            client.connect(("127.0.0.1", server.sockets[0].getsockname()[1]))
            client.sendall(b"request")
            await asyncio.wait_for(started.wait(), 5)
            # Use closesocket without asyncio's shutdown-before-close path:
            # a graceful FIN deliberately keeps the response half alive.
            linger = struct.pack("HH" if os.name == "nt" else "ii", 1, 0)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
            client.close()
            await asyncio.wait_for(done.wait(), 10)
            assert len(children) == 1 and children[0].returncode is not None
            assert slots._value == 1
        finally:
            client.close()
            server.close()
            # Surface assertion/time-out failures, never hang in Server cleanup.
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await asyncio.wait_for(child.wait(), 5)
            await asyncio.wait_for(server.wait_closed(), 10)

    asyncio.run(exercise())


def test_service_shutdown_reaps_active_helper_before_server_closure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    state = tmp_path / "bridge-state.json"
    monkeypatch.setattr(host, "_state_path", lambda: state)
    original_server = asyncio.start_server
    original_spawn = asyncio.create_subprocess_exec
    servers, children = [], []

    async def exercise():
        started = asyncio.Event()

        async def start(callback, address, port, **kwargs):
            server = await original_server(callback, address, 0, **kwargs)
            servers.append(server)
            return server

        async def spawn(*args, **kwargs):
            process = await original_spawn(
                sys.executable, "-u", "-c", "import time; time.sleep(300)", **kwargs
            )
            children.append(process)
            started.set()
            return process

        monkeypatch.setattr(host.asyncio, "start_server", start)
        monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)
        service = asyncio.create_task(host.serve())
        client = None
        try:
            async with asyncio.timeout(5):
                while not state.exists():
                    await asyncio.sleep(0.01)
            assert len(servers) == 2
            _reader, client = await asyncio.open_connection(
                "127.0.0.1", servers[0].sockets[0].getsockname()[1]
            )
            client.write(b"request")
            await client.drain()
            await asyncio.wait_for(started.wait(), 5)
            service.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(service, 15)
            assert not state.exists()
            assert len(children) == 1 and children[0].returncode is not None
            assert all(not server.is_serving() for server in servers)
        finally:
            if client:
                client.close()
                with contextlib.suppress(OSError):
                    await client.wait_closed()
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await asyncio.wait_for(child.wait(), 5)
            if not service.done():
                service.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(service, 15)

    asyncio.run(exercise())


def test_service_forces_closed_backpressured_client_during_shutdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    state = tmp_path / "bridge-state.json"
    monkeypatch.setattr(host, "_state_path", lambda: state)
    original_server = asyncio.start_server
    original_spawn = asyncio.create_subprocess_exec
    servers, children, writers = [], [], []
    drain_state = {"inside": 0}

    async def exercise():
        started = asyncio.Event()

        async def start(callback, address, port, **kwargs):
            async def capturing(reader, writer):
                writers.append(writer)
                original_drain = writer.drain

                async def instrumented():
                    drain_state["inside"] += 1
                    try:
                        await original_drain()
                    finally:
                        drain_state["inside"] -= 1

                # accepted is a plain callback; only await an awaitable.
                writer.drain = instrumented
                result = callback(reader, writer)
                if result is not None:
                    await result

            server = await original_server(capturing, address, 0, **kwargs)
            servers.append(server)
            return server

        async def spawn(*args, **kwargs):
            # Stream far more than socket buffers hold while the client
            # never reads, so graceful drain could never finish.
            process = await original_spawn(
                sys.executable,
                "-u",
                "-c",
                "import sys\nfor _ in range(512):\n sys.stdout.buffer.write(b'x' * 32768)\n",
                **kwargs,
            )
            children.append(process)
            started.set()
            return process

        monkeypatch.setattr(host.asyncio, "start_server", start)
        monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)
        service = asyncio.create_task(host.serve())
        client = None
        try:
            async with asyncio.timeout(5):
                while not state.exists():
                    await asyncio.sleep(0.01)
            reader, client = await asyncio.open_connection(
                "127.0.0.1", servers[0].sockets[0].getsockname()[1]
            )
            client.write(b"request")
            await client.drain()
            await asyncio.wait_for(started.wait(), 5)
            # Prove the download reached a genuinely blocked drain: the
            # instrumented drain must stay suspended across a settle delay
            # (16 MiB backlog, this client never reads), otherwise shutdown
            # would exercise no backpressure path.
            async with asyncio.timeout(10):
                while True:
                    if drain_state["inside"]:
                        await asyncio.sleep(0.2)
                        if drain_state["inside"]:
                            break
                    await asyncio.sleep(0.01)
            service.cancel()
            # The forced close must keep shutdown far inside TimeoutStopSec.
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(service, 15)
            assert not state.exists()
            assert len(children) == 1 and children[0].returncode is not None
            # The forced close discards the backlog instead of draining all
            # 16 MiB before EOF; a graceful close would only finish after
            # this read loop drained everything. Kernel auto-tuning may
            # deliver a few MiB that were already in flight, so only the
            # full-stream amount would prove a graceful drain.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 10
            received = 0
            while True:
                remaining = deadline - loop.time()
                chunk = await asyncio.wait_for(reader.read(1 << 16), remaining)
                if not chunk:
                    break
                received += len(chunk)
            assert 0 < received < (15 << 20), received
        finally:
            if client:
                client.close()
                with contextlib.suppress(OSError):
                    await client.wait_closed()
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await asyncio.wait_for(child.wait(), 5)
            if not service.done():
                service.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(service, 15)

    asyncio.run(exercise())


def test_service_closes_client_cancelled_before_handler_first_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    state = tmp_path / "early-cancel-state.json"
    monkeypatch.setattr(host, "_state_path", lambda: state)
    callbacks, entered = [], []
    original_create = asyncio.create_task

    class Writer:
        closed = False
        transport = None

        def close(self):
            self.closed = True

    writer = Writer()

    class Server:
        def close(self):
            pass

        async def wait_closed(self):
            assert writer.closed

    async def start(callback, *args, **kwargs):
        callbacks.append(callback)
        return Server()

    async def blocked_relay(*args):
        entered.append(True)
        await asyncio.Future()

    def create(coroutine):
        task = original_create(coroutine)
        task.cancel()  # before the coroutine can install its finally
        return task

    monkeypatch.setattr(host.asyncio, "start_server", start)
    monkeypatch.setattr(host.asyncio, "create_task", create)
    monkeypatch.setattr(host, "_relay", blocked_relay)

    async def exercise():
        service = original_create(host.serve())
        try:
            async with asyncio.timeout(5):
                while not state.exists():
                    await asyncio.sleep(0.01)
            callbacks[0](None, writer)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not entered and writer.closed
            service.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(service, 2)
            assert not state.exists()
        finally:
            writer.close()
            if not service.done():
                service.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(service, 2)

    asyncio.run(exercise())


def test_doctor_inspects_only_running_distros_and_never_repairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "windows-full")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        names = (
            "Ubuntu\n"
            if "--running" in command
            else "Ubuntu\nStopped\ndocker-desktop\n"
        )
        return subprocess.CompletedProcess(command, 0, names.encode("utf-16-le"), b"")

    def run_text(command, **kwargs):
        calls.append(command)
        output = "/mapped/checker.py" if "wslpath" in command else json.dumps(_wsl())
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(host.subprocess, "run", run)
    monkeypatch.setattr(host, "_run", run_text)
    rows = host.check()
    assert any(
        row[0] == "WARN" and "Stopped" in row[2] and "uninspected" in row[2]
        for row in rows
    )
    assert not any(
        "Stopped" in command or "docker-desktop" in command for command in calls
    )
    assert not any(
        arg
        in {"--install", "install", "enable", "start", "stop", "restart", "uninstall"}
        for command in calls
        for arg in command
    )


def test_windows_ci_runs_these_tests_on_windows() -> None:
    # The PowerShell classifiers skip on ubuntu-latest; only this job runs them.
    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/unit-test.yaml"
    ).read_text(encoding="utf-8")
    job = workflow.split("\n  windows-ollama-host:\n", 1)[-1].split("\n  windows-", 1)[
        0
    ]
    assert "runs-on: windows-latest" in job
    assert "uvx pytest -q -ra tests/unit/test_ollama_host.py" in job


def test_the_probe_travels_on_stdin_not_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Windows caps a command line at 32,767 characters, and -EncodedCommand
    # doubles and base64-expands the script; the probe is longer than that.
    calls = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs.get("input")))
        return subprocess.CompletedProcess(args, 0, '{"listeners":[],"errors":[]}', "")

    monkeypatch.setattr(host, "_run", run)
    monkeypatch.setattr(host, "powershell", lambda: "powershell.exe")
    host.windows_snapshot()
    args, sent = calls[0]
    assert sent == host.WINDOWS_PROBE
    assert sum(len(arg) + 1 for arg in args) < 8191
    assert host.WINDOWS_PROBE.isascii()
