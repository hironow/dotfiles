#!/usr/bin/env python3
# dotfiles-managed: Windows Ollama client/bridge v1
"""One Windows Scoop Ollama Full; WSL is a loopback-only interop client.

--check never repairs. --setup starts the Windows app or manages the user bridge.
The bridge checks Windows listener ownership BEFORE opening every transport,
including after backend failure, to prevent WSL localhost-forwarding recursion.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import ipaddress
import json
import ntpath
import os
import platform
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

UNIT_MARKER = "# dotfiles-managed: Windows-owned Ollama bridge v1"
UNIT = "ollama-windows-bridge.service"
SOURCE = Path(__file__).resolve()
HELPER_MARKER = "# dotfiles-managed: Windows Ollama client/bridge v1"
CLI_MARKER = "# dotfiles-managed: Windows Ollama CLI client v1"
DURABLE_PYTHON = "/usr/bin/python3"
LOOPBACK = "http://127.0.0.1:11434/api/version"
MAX_CONNECTIONS = 8

# Fixed code, not interpolated shell arguments. Never emit command lines or keys.
WINDOWS_FORWARDER_CLASSIFIER = r"""
# Inherited PowerShell 7 module paths can break Windows PowerShell 5 autoload.
# This diagnostic child needs only its own trusted Windows builtin modules.
$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')
$ProgressPreference='SilentlyContinue'
function Test-DotfilesWslForwarder([string]$Executable,[string]$Address,[int]$Port){
  if($Address -ne '::1' -or $Port -ne 11434){return $false}
  $expected=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'WSL\wslrelay.exe'
  try{
    $actual=Get-Item -LiteralPath $Executable -ErrorAction Stop
    $protected=Get-Item -LiteralPath $expected -ErrorAction Stop
    $parent=Get-Item -LiteralPath (Split-Path -Parent $expected) -ErrorAction Stop
    if($actual.FullName -ine $protected.FullName -or ($actual.Attributes -band [IO.FileAttributes]::ReparsePoint) -or ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint)){return $false}
    $signature=Get-AuthenticodeSignature -FilePath $actual.FullName -ErrorAction Stop
    return [string]$signature.Status -eq 'Valid' -and $signature.SignerCertificate.Subject -match '(^|,\s*)O=Microsoft Corporation(,|$)'
  }catch{return $false}
}
"""
# Decisions on a declared Tailscale forward of 11434 (docs/runbook/ollama-windows-wsl.md).
# Pure: every input comes in as an argument from Get-DotfilesTailnetFacts. Each
# returns '' to accept, or the reason it refuses.
WINDOWS_TAILNET_CLASSIFIER = r"""
function Test-DotfilesTargetPort([string]$Target,[int]$Port){
  if(-not $Target -or $Target.StartsWith('unix:')){return $false}
  $authority=(($Target -replace '^[A-Za-z][A-Za-z0-9+.-]*://','') -split '/',2)[0]
  if($authority -match '^\d+$'){$digits=$authority}elseif($authority -match ':(\d+)$'){$digits=$Matches[1]}else{return $false}
  return $digits.TrimStart('0') -eq [string]$Port
}
function Test-DotfilesServeConfig($Config,[bool]$LoopbackV6Taken){
  if($null -eq $Config){return 'no serve configuration'}
  # Foreground sessions win over the background config, so read them all.
  $sessions=[Collections.Generic.List[object]]::new()
  $sessions.Add(@{Config=$Config;Background=$true})
  if($Config.PSObject.Properties['Foreground']){foreach($entry in $Config.Foreground.PSObject.Properties){$sessions.Add(@{Config=$entry.Value;Background=$false})}}
  foreach($session in $sessions){
    $c=$session.Config
    if($c.PSObject.Properties['AllowFunnel']){foreach($entry in $c.AllowFunnel.PSObject.Properties){if($entry.Value -eq $true){return 'Funnel is on'}}}
  }
  $forward=$null
  foreach($session in $sessions){
    $c=$session.Config
    $groups=[Collections.Generic.List[object]]::new()
    $groups.Add(@{TCP=$c.TCP;Web=$c.Web;Primary=$session.Background})
    if($c.PSObject.Properties['Services']){
      foreach($service in $c.Services.PSObject.Properties){
        if($service.Value.Tun -eq $true){return 'a Tun service forwards every port'}
        $groups.Add(@{TCP=$service.Value.TCP;Web=$service.Value.Web;Primary=$false})
      }
    }
    foreach($group in $groups){
      if($group.TCP){foreach($entry in $group.TCP.PSObject.Properties){
        if($entry.Name -eq '11434'){
          if(-not $group.Primary){return 'another serve handler takes port 11434'}
          $forward=$entry.Value
        }elseif(Test-DotfilesTargetPort ([string]$entry.Value.TCPForward) 11434){return "the forward of port $($entry.Name) also reaches 11434"}
      }}
      if($group.Web){foreach($site in $group.Web.PSObject.Properties){
        if($site.Name -match ':11434$'){return 'a web handler takes port 11434'}
        if($site.Value.Handlers){foreach($handler in $site.Value.Handlers.PSObject.Properties){
          if(Test-DotfilesTargetPort ([string]$handler.Value.Proxy) 11434){return 'a web proxy also reaches 11434'}
        }}
      }}
    }
  }
  if($null -eq $forward){return 'no TCP forward of port 11434'}
  if($forward.HTTPS -or $forward.HTTP -or $forward.TerminateTLS -or $forward.ProxyProtocol){return 'the forward of port 11434 is not a plain TCP forward'}
  $target=[string]$forward.TCPForward
  if($target -eq '127.0.0.1:11434'){return ''}
  if($target -eq 'localhost:11434'){
    # localhost may resolve to ::1, where something other than the backend listens.
    if($LoopbackV6Taken){return 'localhost may reach the listener on [::1]:11434 instead of the backend'}
    return ''
  }
  return "port 11434 is forwarded to $target"
}
function Test-DotfilesTailnetAddress([string]$Address,[string[]]$NodeAddresses){
  try{$ip=[Net.IPAddress]::Parse($Address)}catch{return $false}
  $known=@()
  foreach($entry in @($NodeAddresses)){if($entry){try{$known+=[Net.IPAddress]::Parse($entry.Trim()).ToString()}catch{}}}
  if($known -notcontains $ip.ToString()){return $false}
  $bytes=$ip.GetAddressBytes()
  # Tailscale's address ranges: 100.64.0.0/10 and fd7a:115c:a1e0::/48.
  if($ip.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork){return $bytes[0] -eq 100 -and ($bytes[1] -band 0xC0) -eq 64}
  return $bytes.Length -eq 16 -and $bytes[0] -eq 0xfd -and $bytes[1] -eq 0x7a -and $bytes[2] -eq 0x11 -and $bytes[3] -eq 0x5c -and $bytes[4] -eq 0xa1 -and $bytes[5] -eq 0xe0
}
function Test-DotfilesTailnetLineage($Facts,[int]$OwnerPid){
  $servicePid=[int]$Facts.Service.ProcessId
  if([string]$Facts.Service.State -ne 'Running' -or $servicePid -le 0){return $false}
  if($OwnerPid -eq $servicePid){return $true}
  $child=$Facts.Processes[$OwnerPid];$parent=$Facts.Processes[$servicePid]
  if($null -eq $child -or $null -eq $parent){return $false}
  # A parent newer than its child is a reused pid, not the child's parent.
  return [int]$child.ParentProcessId -eq $servicePid -and [string]$child.Name -ieq 'tailscaled.exe' -and $parent.CreationDate -is [datetime] -and $child.CreationDate -is [datetime] -and $parent.CreationDate -le $child.CreationDate
}
function Test-DotfilesTailnetForward($Facts,[string]$Address,[int]$Port,[int]$OwnerPid){
  if($null -eq $Facts -or -not $Facts.Declared){return 'not declared on this machine'}
  if($Facts.Error){return [string]$Facts.Error}
  if($Port -ne 11434){return 'not port 11434'}
  if(-not (Test-DotfilesTailnetLineage $Facts $OwnerPid)){return 'the listener is not the Tailscale service or its tailscaled child'}
  if(-not $Facts.ServiceBinaryTrusted){return 'the Tailscale service is not the signed tailscaled.exe under Program Files'}
  if(-not (Test-DotfilesTailnetAddress $Address $Facts.NodeAddresses)){return 'not a tailnet address of this machine'}
  return [string](Test-DotfilesServeConfig $Facts.Serve $Facts.LoopbackV6Taken)
}
"""
# Each outside call the probe body makes through a named function, so a test can
# replace it between these definitions and WINDOWS_PROBE_BODY.
WINDOWS_PROBE_FUNCTIONS = r"""
function Test-DotfilesSignedBinary([string]$Path,[string]$Organization){
  try{
    $item=Get-Item -LiteralPath $Path -ErrorAction Stop
    $parent=Get-Item -LiteralPath (Split-Path -Parent $Path) -ErrorAction Stop
    if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint)){return $false}
    $signature=Get-AuthenticodeSignature -FilePath $item.FullName -ErrorAction Stop
    return [string]$signature.Status -eq 'Valid' -and $signature.SignerCertificate.Subject -match ('(^|,\s*)O='+[regex]::Escape($Organization)+'(,|$)')
  }catch{return $false}
}
function Read-DotfilesTailnetDeclaration{
  try{return ([IO.File]::ReadAllText((Join-Path $env:USERPROFILE '.config\dotfiles\ollama-tailnet-forward'))).Trim() -eq '11434'}catch{return $false}
}
function Invoke-DotfilesTailscale([string[]]$Arguments){
  $cli=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Tailscale\tailscale.exe'
  if(-not (Test-DotfilesSignedBinary $cli 'Tailscale Inc.')){throw 'the Tailscale CLI is not the signed one under Program Files'}
  $start=[Diagnostics.ProcessStartInfo]::new()
  $start.FileName=$cli;$start.Arguments=($Arguments -join ' ')
  $start.UseShellExecute=$false;$start.CreateNoWindow=$true
  $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
  $run=[Diagnostics.Process]::new();$run.StartInfo=$start
  try{
    [void]$run.Start()
    $output=$run.StandardOutput.ReadToEndAsync();[void]$run.StandardError.ReadToEndAsync()
    if(-not $run.WaitForExit(5000)){$run.Kill();[void]$run.WaitForExit(1000);throw 'the Tailscale CLI timed out'}
    if($run.ExitCode -ne 0){throw 'the Tailscale CLI failed'}
    return $output.GetAwaiter().GetResult()
  }finally{$run.Dispose()}
}
function Get-DotfilesTailnetFacts([bool]$LoopbackV6Taken){
  # Undeclared machines run no Tailscale command at all.
  if(-not (Read-DotfilesTailnetDeclaration)){return @{Declared=$false}}
  try{
    $service=Get-CimInstance Win32_Service -Filter "Name='Tailscale'" -ErrorAction Stop
    if($null -eq $service){return @{Declared=$true;Error='the Tailscale service is not installed'}}
    $processes=@{}
    foreach($entry in @(Get-CimInstance Win32_Process -Filter "Name='tailscaled.exe'" -ErrorAction Stop)){
      $processes[[int]$entry.ProcessId]=@{ParentProcessId=[int]$entry.ParentProcessId;Name=[string]$entry.Name;CreationDate=$entry.CreationDate}
    }
    $expected=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'Tailscale\tailscaled.exe'
    $binary=([string]$service.PathName).Trim()
    if($binary.StartsWith('"')){$binary=$binary.Substring(1).Split('"')[0]}
    $addresses=@((Invoke-DotfilesTailscale @('ip','-4')) -split '\s+')+@((Invoke-DotfilesTailscale @('ip','-6')) -split '\s+')
    $serve=(Invoke-DotfilesTailscale @('serve','status','--json'))|ConvertFrom-Json
    return @{
      Declared=$true;Error=''
      Service=@{State=[string]$service.State;ProcessId=[int]$service.ProcessId}
      Processes=$processes
      ServiceBinaryTrusted=($binary -ieq $expected -and (Test-DotfilesSignedBinary $expected 'Tailscale Inc.'))
      NodeAddresses=@($addresses|Where-Object{$_})
      Serve=$serve
      LoopbackV6Taken=$LoopbackV6Taken
    }
  }catch{return @{Declared=$true;Error='the declared tailnet forward could not be inspected'}}
}
function Confirm-DotfilesTailnetFacts($Facts){
  # The service pid read again after the checks: a restart in between voids them.
  try{
    $service=Get-CimInstance Win32_Service -Filter "Name='Tailscale'" -ErrorAction Stop
    return $null -ne $service -and [string]$service.State -eq 'Running' -and [int]$service.ProcessId -eq [int]$Facts.Service.ProcessId
  }catch{return $false}
}
function Get-DotfilesBackendVersion{
  $request=[Net.HttpWebRequest]::Create('http://127.0.0.1:11434/api/version')
  $request.Proxy=$null;$request.Timeout=2000;$request.ReadWriteTimeout=2000
  $response=$request.GetResponse()
  try{$reader=[IO.StreamReader]::new($response.GetResponseStream());return ($reader.ReadToEnd()|ConvertFrom-Json).version}finally{$response.Dispose()}
}
"""
WINDOWS_PROBE_BODY = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$errorsList=[Collections.Generic.List[string]]::new()
$scoop=if($env:SCOOP){$env:SCOOP}else{Join-Path $env:USERPROFILE 'scoop'}
$full=Join-Path $scoop 'apps\ollama-full\current'
$physical=''; $bucket=''; $aliases=@()
if(Test-Path $full){
  $aliases+= $full
  $item=Get-Item $full
  $physical=if($item.Target){[string]$item.Target}else{$full}
  $aliases+= $physical
  foreach($name in @('scoop-install.json','install.json')){
    $meta=Join-Path $full $name
    if(Test-Path $meta){$bucket=(Get-Content -Raw $meta|ConvertFrom-Json).bucket;break}
  }
}
$duplicates=[Collections.Generic.List[string]]::new()
foreach($path in @((Join-Path $scoop 'apps\ollama'),(Join-Path $env:LOCALAPPDATA 'Programs\Ollama'),(Join-Path $env:ProgramFiles 'Ollama'))){
  if(Test-Path $path){$duplicates.Add($path)}
}
Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Ollama.Ollama_*') -ErrorAction SilentlyContinue|ForEach-Object{$duplicates.Add($_.FullName)}
foreach($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')){
  Get-ItemProperty $key -ErrorAction SilentlyContinue|Where-Object{$_.DisplayName -match '^Ollama(\s|$)'}|ForEach-Object{$duplicates.Add('registered installer: '+$_.PSChildName)}
}
$listeners=@();$processRows=@()
$tailnetRefusals=[Collections.Generic.List[object]]::new()
try{
  $processes=@(Get-CimInstance Win32_Process -Filter "Name='ollama.exe' OR Name='ollama app.exe'")
  $servers=@($processes|Where-Object{$_.Name -eq 'ollama.exe' -and $_.CommandLine -notmatch '\srunner(\s|$)'}|ForEach-Object{$_.ProcessId})
  $sockets=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Where-Object{$_.LocalPort -eq 11434 -or $_.OwningProcess -in $servers})
  $tailnetFacts=Get-DotfilesTailnetFacts (@($sockets|Where-Object{$_.LocalAddress -eq '::1' -and $_.LocalPort -eq 11434}).Count -gt 0)
  $listeners=@($sockets|ForEach-Object{
    $owner=Get-Process -Id $_.OwningProcess -ErrorAction Stop
    $forwarder=Test-DotfilesWslForwarder $owner.Path $_.LocalAddress $_.LocalPort
    $reason=Test-DotfilesTailnetForward $tailnetFacts ([string]$_.LocalAddress) ([int]$_.LocalPort) ([int]$_.OwningProcess)
    if($tailnetFacts.Declared -and $reason -and -not [Net.IPAddress]::IsLoopback([Net.IPAddress]::Parse([string]$_.LocalAddress))){$tailnetRefusals.Add(@{address=[string]$_.LocalAddress;reason=$reason})}
    @{address=$_.LocalAddress;port=$_.LocalPort;pid=$_.OwningProcess;path=$owner.Path;windows_forwarder=$forwarder;tailnet_forward=($reason -eq '')}
  })
  if(@($listeners|Where-Object{$_.tailnet_forward}).Count -and -not (Confirm-DotfilesTailnetFacts $tailnetFacts)){
    foreach($entry in $listeners){if($entry.tailnet_forward){$entry.tailnet_forward=$false;$tailnetRefusals.Add(@{address=[string]$entry.address;reason='the Tailscale service changed during the check'})}}
  }
  $shimExe=Join-Path $scoop 'shims\ollama.exe'
  $shimConfig=Join-Path $scoop 'shims\ollama.shim'
  $shimTrusted=(Test-Path $shimConfig) -and (Get-Content -Raw $shimConfig).Trim() -eq ('path = "'+$full+'\ollama.exe"')
  $processRows=@($processes|ForEach-Object{
    @{pid=$_.ProcessId;path=$_.ExecutablePath;trusted_shim=($_.ExecutablePath -eq $shimExe -and $shimTrusted)}
  })
}catch{$errorsList.Add('Windows process/listener inventory unavailable')}
$version=''
# Do NOT make a loopback health request without a canonical native owner:
# Windows localhost may otherwise forward back into the WSL bridge.
$backendListeners=@($listeners|Where-Object{-not($_.windows_forwarder -eq $true -and $_.address -eq '::1' -and $_.port -eq 11434) -and -not($_.tailnet_forward -eq $true -and $_.port -eq 11434)})
$owned=$backendListeners.Count -gt 0 -and $physical -ne '' -and $duplicates.Count -eq 0 -and $bucket -eq 'extras'
if(-not @($backendListeners|Where-Object{$_.address -eq '127.0.0.1' -and $_.port -eq 11434}).Count){$owned=$false}
foreach($entry in $backendListeners){
  if($entry.port -ne 11434 -or $entry.address -notin @('127.0.0.1','::1') -or -not (@($aliases|Where-Object{$entry.path -and $entry.path.StartsWith($_+'\',[StringComparison]::OrdinalIgnoreCase)}).Count)){$owned=$false}
}
if($owned -and @($backendListeners.pid|Select-Object -Unique).Count -eq 1){
  try{$version=Get-DotfilesBackendVersion}catch{$errorsList.Add('canonical Windows backend did not return a version')}
}
$miseDir=''
foreach($scope in @('Process','User','Machine')){
  $candidateRoot=[Environment]::GetEnvironmentVariable('MISE_DATA_DIR',$scope)
  if($candidateRoot -match '^[A-Za-z]:[\\/]|^\\\\'){$miseDir=$candidateRoot;break}
}
if(-not $miseDir){$miseDir=Join-Path $env:LOCALAPPDATA 'mise'}
$python='';$pythonError='no validated Windows mise Python >=3.12 available'
$pythonRoot=Join-Path $miseDir 'installs\python'
$candidates=@(Get-ChildItem $pythonRoot -Directory -ErrorAction SilentlyContinue|Where-Object{$_.Name -match '^\d+\.\d+\.\d+$'}|Sort-Object {[version]$_.Name} -Descending|Select-Object -First 3)
foreach($folder in $candidates){
  $candidate=Join-Path $folder.FullName 'python.exe'
  if(-not(Test-Path $candidate)){continue}
  $probeCode='import sys,os,json;print(json.dumps(dict(platform=sys.platform,executable=os.path.realpath(sys.executable),expected=os.path.realpath(sys.argv[1]),prefix=os.path.realpath(sys.prefix),base=os.path.realpath(sys.base_prefix),version=list(sys.version_info[:3]))))'
  $start=[Diagnostics.ProcessStartInfo]::new()
  $start.FileName=$candidate
  $start.Arguments='-I -S -B -c "'+$probeCode+'" "'+$candidate+'"'
  $start.UseShellExecute=$false;$start.CreateNoWindow=$true
  $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
  $probe=[Diagnostics.Process]::new();$probe.StartInfo=$start
  try{
    [void]$probe.Start()
    $output=$probe.StandardOutput.ReadToEndAsync();$probeError=$probe.StandardError.ReadToEndAsync()
    if(-not $probe.WaitForExit(3000)){
      $probe.Kill();[void]$probe.WaitForExit(1000)
      $pythonError='isolated Windows Python validation timed out';continue
    }
    if($probe.ExitCode -ne 0){continue}
    $observed=$output.GetAwaiter().GetResult()|ConvertFrom-Json
    if($observed.platform -eq 'win32' -and $observed.executable -eq $observed.expected -and $observed.prefix -eq $observed.base -and [version]($observed.version -join '.') -ge [version]'3.12.0'){
      $python=$observed.executable;$pythonError='';break
    }
  }catch{$pythonError='isolated Windows Python validation failed'}finally{$probe.Dispose()}
}
$allowedHost=@('','127.0.0.1:11434','http://127.0.0.1:11434','localhost:11434','http://localhost:11434','[::1]:11434','http://[::1]:11434')
$conflictingConfig=$false
foreach($scope in @('Process','User','Machine')){
  $hostValue=[Environment]::GetEnvironmentVariable('OLLAMA_HOST',$scope)
  if($hostValue -and $hostValue.TrimEnd('/') -notin $allowedHost){$conflictingConfig=$true}
}
@{full_dir=$physical;full_paths=@($aliases);full_bucket=$bucket;duplicates=@($duplicates);listeners=@($listeners);processes=@($processRows);python=$python;python_error=$pythonError;version=$version;conflicting_config=$conflictingConfig;tailnet_refusals=@($tailnetRefusals);errors=@($errorsList)}|ConvertTo-Json -Depth 5 -Compress
"""
WINDOWS_PROBE = (
    WINDOWS_FORWARDER_CLASSIFIER
    + WINDOWS_TAILNET_CLASSIFIER
    + WINDOWS_PROBE_FUNCTIONS
    + WINDOWS_PROBE_BODY
)


_CONTAINER_SENTINELS = (Path("/.dockerenv"), Path("/run/.containerenv"))


def _in_container() -> bool:
    if sys.platform != "linux":
        return False
    return any(sentinel.exists() for sentinel in _CONTAINER_SENTINELS)


def host_policy(
    system: str | None = None,
    release: str | None = None,
    container: bool | None = None,
) -> str | None:
    system = sys.platform if system is None else system
    release = platform.release() if release is None else release
    if system == "win32":
        return "windows-full"
    if system != "linux" or "microsoft" not in release.lower():
        return None
    # Containers on a WSL2 host inherit the Microsoft kernel but have no
    # Windows interop or user systemd; the singleton policy is inapplicable.
    return (
        None if (_in_container() if container is None else container) else "wsl-client"
    )


def _inside(path: str, root: str) -> bool:
    return bool(path and root) and ntpath.normcase(ntpath.normpath(path)).startswith(
        ntpath.normcase(ntpath.normpath(root)).rstrip("\\") + "\\"
    )


def _loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def _wsl_forwarder(row: dict) -> bool:
    """The signed Microsoft ::1 forwarder the probe verified, not a backend."""
    return (
        row.get("windows_forwarder") is True
        and row.get("address") == "::1"
        and row.get("port", 11434) == 11434
    )


def _tailnet_forward(row: dict) -> bool:
    """A Tailscale forward of 11434 the probe verified against this machine's
    declaration (tailnet only, no Funnel), not a backend."""
    return row.get("tailnet_forward") is True and row.get("port", 11434) == 11434


def _backend_listeners(data: dict) -> list[dict]:
    return [
        row
        for row in data.get("listeners", [])
        if not _wsl_forwarder(row) and not _tailnet_forward(row)
    ]


def backend_owned(data: dict) -> bool:
    rows = windows_findings(data)
    return (
        not any(row[0] != "OK" for row in rows if row[1] != "ollama-transport")
        and isinstance(data.get("version"), str)
        and bool(data["version"])
    )


def windows_findings(data: dict) -> list[tuple[str, str, str]]:
    rows = []
    roots = data.get("full_paths") or [data.get("full_dir", "")]
    listeners = data.get("listeners", [])
    owners = {row.get("pid") for row in listeners}
    duplicates = list(data.get("duplicates", []))
    for process in data.get("processes", []):
        path = process.get("path", "")
        if (
            path
            and not any(_inside(path, root) for root in roots)
            and not (process.get("trusted_shim") and process.get("pid") not in owners)
        ):
            duplicates.append("running outside canonical full: " + path)
    good_install = (
        data.get("full_dir") and data.get("full_bucket") == "extras" and not duplicates
    )
    rows.append(
        (
            "OK" if good_install else "ERR",
            "ollama-install",
            "Scoop extras/ollama-full is the sole installation"
            if good_install
            else "require only Scoop extras/ollama-full; remove duplicate CLI/WinGet/standalone installations: "
            + ", ".join(duplicates),
        )
    )
    backends = _backend_listeners(data)
    owned = (
        any(
            row.get("address") == "127.0.0.1" and row.get("port", 11434) == 11434
            for row in backends
        )
        and len({row.get("pid") for row in backends}) == 1
        and all(
            any(_inside(row.get("path", ""), root) for root in roots)
            and row.get("port", 11434) == 11434
            for row in backends
        )
    )
    rows.append(
        (
            "OK" if owned else "ERR" if backends else "WARN",
            "ollama-owner",
            "one canonical Windows backend owns 127.0.0.1:11434"
            if owned
            else "no canonical Windows backend, conflicting owner, or multiple serving backends",
        )
    )
    if any(_wsl_forwarder(row) for row in listeners):
        rows.append(
            (
                "OK",
                "ollama-wsl-forwarder",
                "verified Microsoft ::1 forwarding listener is not another Ollama backend",
            )
        )
    refusals = data.get("tailnet_refusals") or []
    if not isinstance(refusals, list):
        refusals = [{"reason": "the probe returned an invalid refusal record"}]
    for refusal in refusals:
        where = refusal.get("address", "?")
        why = refusal.get("reason", "unverified")
        rows.append(
            (
                "ERR",
                "ollama-tailnet-forward",
                f"declared tailnet forward refused on {where}: {why}",
            )
        )
    if not refusals and any(_tailnet_forward(row) for row in listeners):
        rows.append(
            (
                "OK",
                "ollama-tailnet-forward",
                "declared tailnet-only Tailscale forward of 11434 (no Funnel) is not a second backend",
            )
        )
    exposed = data.get("conflicting_config", False) or any(
        not _loopback(row.get("address", ""))
        for row in listeners
        if not _tailnet_forward(row)
    )
    rows.append(
        (
            "ERR" if exposed else "OK",
            "ollama-exposure",
            "non-loopback Windows listener or conflicting OLLAMA_HOST detected"
            if exposed
            else "no non-loopback Windows Ollama listener",
        )
    )
    if not isinstance(data.get("version"), str) or not data["version"]:
        rows.append(
            (
                "WARN",
                "ollama-health",
                "canonical backend health unverified; start the Windows Ollama full application",
            )
        )
    if not data.get("python"):
        rows.append(
            (
                "WARN",
                "ollama-transport",
                data.get(
                    "python_error",
                    "validated Windows mise Python missing; WSL sharing unavailable",
                ),
            )
        )
    if data.get("errors"):
        rows.append(("WARN", "ollama-inspection", "; ".join(data["errors"])))
    return rows


def wsl_findings(
    data: dict, windows_version: str | None = None
) -> list[tuple[str, str, str]]:
    rows = []
    native = data.get("native", []) + data.get("services", [])
    rows.append(
        (
            "ERR" if native else "OK",
            "ollama-wsl-native",
            "native binary/package/process/service remains: " + ", ".join(native)
            if native
            else "no inspected native Ollama installation or service",
        )
    )
    if data.get("models"):
        rows.append(
            (
                "ERR",
                "ollama-wsl-models",
                "WSL model storage exists; Windows must own model/authentication state (no automatic deletion)",
            )
        )
    identity = all(
        data.get(key)
        for key in ("client_managed", "bridge_managed", "bridge_active", "bridge_owned")
    )
    if not identity:
        state, message = (
            "ERR",
            "managed client, bridge service, socket ownership, or end-to-end check failed; rerun ollama_host.py --setup",
        )
    elif not isinstance(data.get("version"), str) or not data["version"]:
        # A correctly managed bridge that cannot reach the backend is an
        # ordinary outage (the runbook's stopped-backend case), not a
        # configuration error; identity failures above remain ERR.
        state, message = (
            "WARN",
            "Windows backend unreachable through the managed bridge; start the canonical Windows Ollama full application or rerun ollama_host.py --setup",
        )
    elif windows_version is not None and data["version"] != windows_version:
        state, message = (
            "ERR",
            f"bridge reached version {data['version']} but Windows reports {windows_version}",
        )
    else:
        state, message = "OK", "managed loopback bridge reaches Windows backend"
    rows.append((state, "ollama-bridge", message))
    rows.append(
        (
            "OK"
            if data.get("loopback_only") and not data.get("conflicting_config")
            else "ERR",
            "ollama-exposure",
            "WSL listener is loopback-only"
            if data.get("loopback_only") and not data.get("conflicting_config")
            else "WSL listener exposure or OLLAMA_HOST conflicts with the managed loopback",
        )
    )
    if data.get("errors"):
        rows.append(("WARN", "ollama-inspection", "; ".join(data["errors"])))
    return rows


def interop_environment() -> dict[str, str]:
    env = os.environ.copy()
    for path in (
        Path(env.get("WSL_INTEROP", "/nonexistent")),
        Path("/run/WSL/1_interop"),
    ):
        if path.is_socket():
            env["WSL_INTEROP"] = str(path)
            return env
    raise RuntimeError("Windows interop unavailable in this context")


def powershell() -> str:
    if sys.platform == "win32":
        return str(
            Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
    candidates = [Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")]
    candidates.extend(
        Path("/mnt").glob("*/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    raise RuntimeError("absolute Windows PowerShell executable unavailable")


def _run(
    args: list[str],
    *,
    timeout: int = 15,
    interop: bool = False,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=interop_environment() if interop else None,
    )


# The probe is longer than a Windows command line can carry (32,767 characters,
# and -EncodedCommand doubles and base64-expands a script). This short fixed
# bootstrap reads the fixed script from standard input as UTF-8 and dot-sources
# it, so it runs in the same scope as if it had been the command itself.
POWERSHELL_STDIN_BOOTSTRAP = "$dotfilesProbe=[IO.StreamReader]::new([Console]::OpenStandardInput(),[Text.UTF8Encoding]::new($false)).ReadToEnd();. ([scriptblock]::Create($dotfilesProbe))"


def run_powershell(
    script: str, *, timeout: int = 15
) -> subprocess.CompletedProcess[str]:
    """Runs fixed Windows PowerShell 5.1 code, passed on standard input."""
    command = base64.b64encode(POWERSHELL_STDIN_BOOTSTRAP.encode("utf-16-le")).decode(
        "ascii"
    )
    return _run(
        [powershell(), "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
        timeout=timeout,
        interop=sys.platform != "win32",
        input=script,
    )


def windows_snapshot() -> dict:
    result = run_powershell(WINDOWS_PROBE)
    if result.returncode:
        raise RuntimeError("Windows inventory did not complete; ownership unverified")
    data = json.loads(result.stdout.lstrip("\ufeff"))
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("listeners"), list)
        or not isinstance(data.get("errors"), list)
    ):
        raise TypeError("Windows inventory returned an invalid schema")
    return data


def _windows_path(path: str) -> str:
    drive, rest = ntpath.splitdrive(path)
    if len(drive) != 2 or drive[1] != ":":
        raise RuntimeError("Windows transport must be on a local drive")
    return "/mnt/" + drive[0].lower() + rest.replace("\\", "/")


WINDOWS_STREAM = r"""
import os, socket, sys, threading, msvcrt
if len(sys.argv) != 3 or sys.argv[1:] != ['127.0.0.1', '11434']:
    os._exit(2)
msvcrt.setmode(0, os.O_BINARY)
msvcrt.setmode(1, os.O_BINARY)
failed = threading.Event()
backend = None
status = 0
try:
    backend = socket.create_connection(('127.0.0.1', 11434), timeout=2)
    # Per-direction timeout: a response silent for 300 seconds also times
    # out during an upload. Continuous responses reset the receive timeout.
    backend.settimeout(300)
    def upload():
        try:
            while data := os.read(0, 32768):
                backend.sendall(data)
            backend.shutdown(socket.SHUT_WR)
        except BaseException:
            failed.set()
            try:
                backend.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    threading.Thread(target=upload, daemon=True).start()
    while data := backend.recv(32768):
        pending = memoryview(data)
        while pending:
            count = os.write(1, pending)
            if count <= 0:
                raise BrokenPipeError()
            pending = pending[count:]
except BaseException:
    status = 1
finally:
    if backend is not None:
        backend.close()
os._exit(1 if failed.is_set() else status)
"""


def transport_command(executable: str) -> list[str]:
    return [
        executable,
        "-I",
        "-S",
        "-B",
        "-u",
        "-c",
        WINDOWS_STREAM,
        "127.0.0.1",
        "11434",
    ]


def _state_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime is None:
        getuid = getattr(os, "getuid", None)
        if not callable(getuid):
            raise RuntimeError("WSL runtime directory unavailable on this platform")
        runtime = f"/run/user/{getuid()}"
    return Path(runtime) / "dotfiles-ollama-bridge.json"


def _source_hash(path: Path | None = None) -> str:
    return hashlib.sha256((SOURCE if path is None else path).read_bytes()).hexdigest()


def deployment_source() -> Path:
    return Path.home() / ".local/lib/dotfiles/ollama_host.py"


def deployment_matches(deployed: Path, checker: Path) -> bool:
    return (
        deployed.is_file()
        and not deployed.is_symlink()
        and HELPER_MARKER in deployed.read_text(encoding="utf-8").splitlines()[:3]
        and _source_hash(deployed)
        == hashlib.sha256(
            checker.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
    )


def cli_wrapper(source: str) -> str:
    return f'#!/bin/sh\n{CLI_MARKER}\nexec {shlex.quote(DURABLE_PYTHON)} {shlex.quote(source)} --cli -- "$@"\n'


def managed_cli(path: Path, source: Path) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and os.access(path, os.X_OK)
        and path.read_text(encoding="utf-8", errors="replace")
        == cli_wrapper(str(source))
    )


def _write_owned(path: Path, text: str, previous_hash: str | None, mode: int) -> None:
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if path.is_symlink() or (
        path.exists()
        and (not path.is_file() or _source_hash(path) not in {previous_hash, expected})
    ):
        raise RuntimeError(
            f"refusing to overwrite unrelated/modified deployment: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".ollama-", delete=False
    ) as file:
        temporary = Path(file.name)
        file.write(text.encode("utf-8"))
    try:
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def install_client_files() -> None:
    # Stable user-owned copy, never a disposable worktree or uv venv path.
    target = deployment_source()
    if target.parent.is_symlink() or not Path(DURABLE_PYTHON).is_file():
        raise RuntimeError("stable deployment directory and /usr/bin/python3 required")
    record_path = target.parent / "ollama-deployment.json"
    if record_path.is_symlink():
        raise RuntimeError("refusing a symlinked deployment manifest")
    record = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if record_path.exists()
        else {}
    )
    if not isinstance(record, dict):
        raise TypeError("deployment manifest must be an object")
    if record_path.exists() and record.get("owner") != HELPER_MARKER:
        raise RuntimeError("refusing an unrelated deployment manifest")
    record["owner"] = HELPER_MARKER
    texts = {
        "helper": (target, SOURCE.read_text(encoding="utf-8"), 0o600),
        "shim": (Path.home() / ".local/bin/ollama", cli_wrapper(str(target)), 0o755),
        "unit": (
            Path.home() / ".config/systemd/user" / UNIT,
            bridge_unit(DURABLE_PYTHON, str(target)),
            0o644,
        ),
    }
    # Preflight all files before making changes; a marker alone grants no ownership.
    for key, (path, text, _mode) in texts.items():
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if path.is_symlink() or (
            path.exists()
            and (
                not path.is_file()
                or _source_hash(path) not in {record.get(key), expected}
            )
        ):
            raise RuntimeError(f"refusing unrelated/modified deployment: {path}")
    for key, (path, text, mode) in texts.items():
        _write_owned(path, text, record.get(key), mode)
        record[key] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _write_owned(
        record_path,
        json.dumps(record, indent=2) + "\n",
        _source_hash(record_path) if record_path.exists() else None,
        0o600,
    )


def client_command(args: list[str]) -> int:
    if host_policy() != "wsl-client":
        raise RuntimeError("managed CLI client runs only in WSL")
    allowed = {
        "create",
        "show",
        "run",
        "stop",
        "pull",
        "push",
        "signin",
        "signout",
        "list",
        "ls",
        "ps",
        "cp",
        "rm",
        "help",
    }
    global_flags = {"-h", "--help", "-v", "--version", "--nowordwrap", "--verbose"}
    for part in args:
        if part.startswith("-"):
            if part not in global_flags:
                raise RuntimeError("unsupported global Ollama flag")
        else:
            if part not in allowed:
                raise RuntimeError(
                    "daemon/menu/unknown entry point refused; use the Windows Full application"
                )
            break
    data = windows_snapshot()
    if not backend_owned(data):
        raise RuntimeError(
            "canonical Windows backend unavailable; no daemon or native fallback"
        )
    env = interop_environment()
    env["OLLAMA_HOST"] = "http://127.0.0.1:11434"
    tokens = [
        token
        for token in env.get("WSLENV", "").split(":")
        if token and token.split("/")[0] != "OLLAMA_HOST"
    ]
    env["WSLENV"] = ":".join(tokens + ["OLLAMA_HOST"])
    executable = _windows_path(ntpath.join(data["full_dir"], "ollama.exe"))
    return subprocess.run(
        [executable, *(args or ["--help"])], env=env, check=False
    ).returncode


def _version() -> str:
    # This is an HTTP byte stream, not a locale-dependent filesystem open.
    http_get = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    with http_get(LOOPBACK, timeout=20) as response:
        data = json.loads(response.read(16384))
        if (
            response.status != 200
            or not isinstance(data, dict)
            or not isinstance(data.get("version"), str)
            or not data["version"]
        ):
            raise RuntimeError("invalid Ollama version response")
        return data["version"]


def managed_unit(text: str, source: str) -> bool:
    try:
        line = next(line for line in text.splitlines() if line.startswith("ExecStart="))
        args = [
            part.replace("%%", "%").replace("$$", "$")
            for part in shlex.split(line.removeprefix("ExecStart="))
        ]
        return (
            len(args) == 3
            and args[1:] == [source, "--serve"]
            and args[0] == DURABLE_PYTHON
            and text == bridge_unit(DURABLE_PYTHON, source)
        )
    except (StopIteration, ValueError):
        return False


def wsl_snapshot() -> dict:
    native = []
    errors = []
    deployed = deployment_source()
    shim = Path.home() / ".local/bin/ollama"
    is_client = managed_cli(shim, deployed)
    helper_valid = deployment_matches(deployed, SOURCE)
    for path in (
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
        Path.home() / ".local/bin/ollama",
        Path("/usr/local/lib/ollama"),
        Path("/usr/lib/ollama"),
        Path("/usr/share/ollama"),
        Path("/var/lib/ollama"),
        Path("/snap/ollama"),
    ):
        if path.exists() and not (path == shim and is_client):
            native.append(str(path))
    found = shutil.which("ollama")
    if (
        found
        and not found.lower().endswith(".exe")
        and found not in native
        and not (Path(found) == shim and is_client)
    ):
        native.append(found)
    if shutil.which("dpkg-query"):
        packages = _run(["dpkg-query", "-W", "-f=${Status}", "ollama"])
        if "install ok installed" in packages.stdout:
            native.append("dpkg:ollama")
    processes = _run(["ps", "-eo", "comm="])
    if any(name.strip() == "ollama" for name in processes.stdout.splitlines()):
        native.append("native ollama process")
    services = []
    for scope in ("--system", "--user"):
        result = _run(
            [
                "systemctl",
                scope,
                "show",
                "ollama.service",
                "-p",
                "LoadState",
                "-p",
                "ActiveState",
                "-p",
                "UnitFileState",
            ]
        )
        if "LoadState=not-found" not in result.stdout:
            if result.returncode:
                errors.append(f"{scope} Ollama service inventory unavailable")
            else:
                services.append(scope + ":" + result.stdout.strip().replace("\n", ":"))
    unit = Path.home() / ".config/systemd/user" / UNIT
    managed = unit.exists() and managed_unit(
        unit.read_text(encoding="utf-8"), str(deployed)
    )
    service = _run(
        ["systemctl", "--user", "show", UNIT, "-p", "ActiveState", "-p", "ExecMainPID"]
    )
    state = {}
    with contextlib.suppress(OSError, ValueError):
        state = json.loads(_state_path().read_text(encoding="utf-8"))
    pid = state.get("pid", 0)
    identity = False
    if pid and helper_valid and state.get("sha256") == _source_hash(deployed):
        with contextlib.suppress(OSError):
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\x00")
            identity = b"--serve" in args and str(deployed).encode() in args
            identity = (
                identity
                and Path(f"/proc/{pid}/exe").resolve() == Path(DURABLE_PYTHON).resolve()
            )
    sockets = _run(["ss", "-H", "-ltnp", "sport = :11434"])
    if sockets.returncode:
        errors.append("WSL socket ownership inventory unavailable")
    if processes.returncode:
        errors.append("WSL process inventory unavailable")
    lines = sockets.stdout.splitlines()
    owned = bool(lines) and identity and all(f"pid={pid}," in line for line in lines)
    addresses = [
        line.split()[3].rsplit(":", 1)[0].strip("[]")
        for line in lines
        if len(line.split()) >= 5
    ]
    loopback_only = bool(addresses) and all(_loopback(address) for address in addresses)
    version = ""
    if owned and loopback_only:
        with contextlib.suppress(OSError, ValueError, RuntimeError):
            version = _version()
    models = Path.home() / ".ollama/models"
    return {
        "native": native,
        "services": services,
        "models": models.is_dir() and any(models.iterdir()),
        "errors": errors,
        "conflicting_config": os.environ.get("OLLAMA_HOST", "").rstrip("/")
        not in {
            "",
            "localhost:11434",
            "http://localhost:11434",
            "127.0.0.1:11434",
            "http://127.0.0.1:11434",
            "[::1]:11434",
            "http://[::1]:11434",
        },
        "client_managed": is_client and helper_valid,
        "bridge_managed": managed,
        "bridge_active": "ActiveState=active" in service.stdout
        and f"ExecMainPID={pid}\n" in service.stdout,
        "bridge_owned": owned,
        "loopback_only": loopback_only,
        "version": version,
    }


def bridge_unit(python: str, source: str) -> str:
    def quote(value: str) -> str:
        return (
            '"'
            + value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("%", "%%")
            .replace("$", "$$")
            + '"'
        )

    return f"{UNIT_MARKER}\n[Unit]\nDescription=Loopback client of Windows Scoop Ollama Full (not an Ollama server)\n\n[Service]\nExecStart={quote(python)} {quote(source)} --serve\nRestart=on-failure\nRestartSec=3\nKillMode=control-group\nTimeoutStopSec=20\n\n[Install]\nWantedBy=default.target\n"


async def _relay(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, slots: asyncio.Semaphore
) -> None:
    process = None
    up = None
    down = None
    acquired = False
    try:
        if slots.locked():
            return
        await slots.acquire()
        acquired = True
        data = await asyncio.to_thread(windows_snapshot)
        # No cached health: a re-entered connection after backend death refuses
        # before Windows helper spawn, rather than reconnecting to itself.
        if not backend_owned(data) or not data.get("python"):
            return
        executable = _windows_path(data["python"])
        process = await asyncio.create_subprocess_exec(
            *transport_command(executable),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=interop_environment(),
        )

        input_pipe, output_pipe = process.stdin, process.stdout
        if input_pipe is None or output_pipe is None:
            raise RuntimeError("binary transport pipes unavailable")

        async def upload() -> None:
            try:
                while chunk := await reader.read(32768):
                    input_pipe.write(chunk)
                    await input_pipe.drain()
            finally:
                input_pipe.close()

        async def download() -> None:
            while chunk := await output_pipe.read(32768):
                writer.write(chunk)
                await writer.drain()

        up = asyncio.create_task(upload())
        down = asyncio.create_task(download())
        done, _pending = await asyncio.wait(
            {up, down}, return_when=asyncio.FIRST_COMPLETED
        )
        if up in done:
            # RST/read failure cancels immediately; a normal FIN is a valid
            # half-close and must still allow the backend response to drain.
            await up
        await down
        if await asyncio.wait_for(process.wait(), timeout=5) != 0:
            raise RuntimeError("isolated Windows byte transport failed")
    except (OSError, RuntimeError, ValueError, TypeError, subprocess.SubprocessError):
        print("WARN ollama-bridge: transport/ownership unavailable", file=sys.stderr)
    finally:
        try:
            for task in (up, down):
                if task:
                    task.cancel()
                    # A second pipe failure must not skip child reaping.
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
            if process:
                if process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        process.terminate()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=5)
                if process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
                # Drain/close pipe transports after reaping; avoid retaining
                # subprocess descriptors past event-loop shutdown on abort.
                with contextlib.suppress(OSError, ValueError, TimeoutError):
                    await asyncio.wait_for(process.communicate(), timeout=5)
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=5)
            except TimeoutError:
                # A client that stops reading pins the graceful drain; force
                # the socket closed so server.wait_closed() cannot outlive
                # the unit's stop timeout.
                transport = writer.transport
                if transport is not None:
                    transport.abort()
            except OSError:
                pass
            # The slot covers the entire child lifetime, including reaping.
            if acquired:
                slots.release()


async def serve() -> None:
    if host_policy() != "wsl-client":
        raise RuntimeError("the bridge runs only in WSL")
    slots = asyncio.Semaphore(MAX_CONNECTIONS)
    servers = []
    active: set[asyncio.Task] = set()
    closing = False

    def finished(task: asyncio.Task, writer: asyncio.StreamWriter) -> None:
        # Cancellation before the coroutine's first step skips its finally.
        transport = writer.transport
        if closing and transport is not None:
            # Shutdown must not wait on a drain that cannot finish.
            transport.abort()
        writer.close()
        active.discard(task)
        if not task.cancelled() and task.exception() is not None:
            print("WARN ollama-bridge: relay handler failed", file=sys.stderr)

    def accepted(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if closing:
            writer.close()
            return
        task = asyncio.create_task(_relay(reader, writer, slots))
        active.add(task)
        task.add_done_callback(lambda done: finished(done, writer))

    state_written = False
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    handles_term = False
    if sys.platform == "linux" and current is not None:
        loop.add_signal_handler(signal.SIGTERM, current.cancel)
        handles_term = True
    try:
        # Bind both explicitly. A conflicting port/address family must fail,
        # not yield a partially managed localhost listener.
        for address, family in (
            ("127.0.0.1", socket.AF_INET),
            ("::1", socket.AF_INET6),
        ):
            servers.append(
                await asyncio.start_server(accepted, address, 11434, family=family)
            )
        state = _state_path()
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            json.dumps({"pid": os.getpid(), "sha256": _source_hash()}), encoding="utf-8"
        )
        state.chmod(0o600)
        state_written = True
        # start_server already serves. serve_forever() cancellation itself
        # waits for active clients, preventing entry into our child cleanup.
        await asyncio.Future()
    finally:
        closing = True
        if handles_term:
            loop.remove_signal_handler(signal.SIGTERM)
        for server in servers:
            server.close()
        handlers = list(active)
        for task in handlers:
            task.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
        for server in servers:
            await server.wait_closed()
        if state_written:
            with contextlib.suppress(FileNotFoundError):
                _state_path().unlink()


def setup() -> None:
    policy = host_policy()
    if policy is None:
        return
    if policy == "wsl-client":
        # Provision compatibility client BEFORE interop/backend availability;
        # an old deploy must not mistake downtime for a missing Linux server.
        install_client_files()
    data = windows_snapshot()
    if policy == "windows-full":
        if (
            not data.get("full_dir")
            or data.get("duplicates")
            or data.get("full_bucket") != "extras"
        ):
            raise RuntimeError(
                "install only Scoop extras/ollama-full on Windows; no standalone installer fallback"
            )
        if any(row[0] == "ERR" for row in windows_findings(data)):
            raise RuntimeError("resolve Ollama configuration violations before startup")
        if not _backend_listeners(data):
            app = Path(data["full_dir"]) / "ollama app.exe"
            subprocess.Popen(
                [str(app)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return
    if policy != "wsl-client":
        return
    local = wsl_snapshot()
    if local["native"] or local["services"]:
        raise RuntimeError(
            "remove conflicting WSL native Ollama before bridge setup; models are never removed automatically"
        )
    if not backend_owned(data) or not data.get("python"):
        raise RuntimeError(
            "canonical Windows Ollama Full + validated Windows mise Python required first"
        )
    if all(
        row[0] == "OK" for row in wsl_findings(local, windows_version=data["version"])
    ):
        return
    for args in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", UNIT],
        ["systemctl", "--user", "restart", UNIT],
    ):
        subprocess.run(args, check=True, timeout=30)


def _decode_wsl(raw: bytes) -> list[str]:
    text = raw.decode("utf-16-le" if b"\x00" in raw else "utf-8", errors="replace")
    return [line.strip().lstrip("\ufeff") for line in text.splitlines() if line.strip()]


def check() -> list[tuple[str, str, str]]:
    policy = host_policy()
    if policy is None:
        return [
            (
                "OK",
                "ollama-policy",
                "Windows/WSL singleton policy not applicable on this host",
            )
        ]
    try:
        data = windows_snapshot()
        rows = windows_findings(data)
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        rows = [("WARN", "ollama-inspection", str(error))]
        data = {}
    if policy == "wsl-client":
        rows += wsl_findings(wsl_snapshot(), windows_version=data.get("version", ""))
    else:
        try:
            all_result = subprocess.run(
                ["wsl.exe", "--list", "--quiet"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            running_result = subprocess.run(
                ["wsl.exe", "--list", "--running", "--quiet"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if all_result.returncode or running_result.returncode:
                raise RuntimeError("WSL distribution inventory unavailable")
            running = _decode_wsl(running_result.stdout)
            for distro in _decode_wsl(all_result.stdout):
                if distro not in running or distro == "docker-desktop":
                    rows.append(
                        (
                            "WARN",
                            "ollama-inspection",
                            f"WSL {distro}: stopped/platform-managed, uninspected (not started)",
                        )
                    )
                    continue
                mapped = _run(
                    ["wsl.exe", "-d", distro, "--exec", "wslpath", "-u", str(SOURCE)]
                )
                result = _run(
                    [
                        "wsl.exe",
                        "-d",
                        distro,
                        "--exec",
                        "python3",
                        mapped.stdout.strip(),
                        "--inspect-local",
                    ],
                    timeout=45,
                )
                if mapped.returncode or result.returncode:
                    rows.append(
                        (
                            "WARN",
                            "ollama-inspection",
                            f"WSL {distro}: inaccessible checker, uninspected",
                        )
                    )
                else:
                    rows += [
                        (severity, name, f"{distro}: {detail}")
                        for severity, name, detail in wsl_findings(
                            json.loads(result.stdout),
                            windows_version=data.get("version", ""),
                        )
                    ]
        except (
            OSError,
            ValueError,
            TypeError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            rows.append(("WARN", "ollama-inspection", str(error)))
    return rows


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ("check", "setup", "serve", "inspect-local", "cli"):
        group.add_argument("--" + flag, action="store_true")
    parser.add_argument("cli_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.cli:
            return client_command(
                args.cli_args[1:] if args.cli_args[:1] == ["--"] else args.cli_args
            )
        if args.inspect_local:
            print(json.dumps(wsl_snapshot()))
        elif args.serve:
            with contextlib.suppress(asyncio.CancelledError):
                asyncio.run(serve())
        elif args.setup:
            setup()
        else:
            rows = check()
            for severity, name, detail in rows:
                print(f"{severity:<4} {name} - {detail}")
            return int(any(row[0] == "ERR" for row in rows))
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"ERR  ollama-policy - {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
