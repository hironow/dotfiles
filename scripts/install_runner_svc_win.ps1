# ==============================================================================
# Install / repair the native Windows GitHub Actions runner SERVICE
# ------------------------------------------------------------------------------
# Windows counterpart of the WSL runner's systemd unit. Idempotent: creates the
# service if absent, re-enables a Disabled one in place, refreshes recovery
# settings, and starts it. Generic across hosts: the runner root comes from
# -RunnerRoot / RUNNER_WIN_ROOT (default %USERPROFILE%\actions-runner-win) and
# every name is derived from the runner's own .runner config.
#
# Runs as LocalSystem (no storable password). LocalSystem resolves tools via
# the MACHINE PATH - the "PATH onion": jobs need the scoop shims, .bun\bin and
# mise shims entries there or they die on `command not found` while the
# service looks healthy. PATH presence proves the shims are findable, NOT
# usable: per-user tool state under the user's profile is not visible to
# SYSTEM, so the only real proof is the next green job.
#
# Needs Administrator; self-elevates via UAC (repo convention, see
# restore_machine_path.ps1). The elevated child gets a fresh console that
# closes on exit and does not inherit the caller's env, so the root is
# forwarded as an explicit argument and all output lands in a transcript
# whose path the parent prints BEFORE elevating.
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$RunnerRoot = '',
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'

if (-not $RunnerRoot) {
    $RunnerRoot = if ($env:RUNNER_WIN_ROOT) { $env:RUNNER_WIN_ROOT }
                  else { Join-Path $env:USERPROFILE 'actions-runner-win' }
}
$logPath = Join-Path $env:TEMP 'runner-svc-install.log'

$runnerCfgPath = Join-Path $RunnerRoot '.runner'
if (-not (Test-Path $runnerCfgPath)) {
    Write-Host "ERROR: $runnerCfgPath not found - the runner is not configured on this host."
    Write-Host '       Configure it first (config.cmd) or point -RunnerRoot/RUNNER_WIN_ROOT at the install.'
    exit 1
}
$binaryPath = Join-Path $RunnerRoot 'bin\RunnerService.exe'
if (-not (Test-Path $binaryPath)) {
    Write-Host "ERROR: $binaryPath not found - broken runner install."
    exit 1
}

# .runner carries a UTF-8 BOM on real hosts; Get-Content decodes it. A
# repo-scoped runner yields gitHubUrl=.../owner/repo - '/' is illegal in a
# service name, GitHub's own installer uses '-'.
$runnerCfg   = Get-Content $runnerCfgPath | ConvertFrom-Json
$owner       = (($runnerCfg.gitHubUrl -replace '^https?://github\.com/', '').TrimEnd('/')) -replace '/', '-'
$runnerName  = $runnerCfg.agentName
$serviceName = "actions.runner.$owner.$runnerName"
$displayName = "GitHub Actions Runner ($owner.$runnerName)"
$account     = 'LocalSystem'

$isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Elevating (approve the UAC prompt); output lands in: $logPath"
    try {
        $psi = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru `
            -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', `
            '-File', "`"$PSCommandPath`"", '-RunnerRoot', "`"$RunnerRoot`"", '-Elevated'
    } catch {
        Write-Host 'ERROR: elevation declined or failed - nothing was changed.'
        exit 1
    }
    Get-Content $logPath -ErrorAction SilentlyContinue
    exit $psi.ExitCode
}

if ($Elevated) { Start-Transcript -Path $logPath -Force | Out-Null }

function Invoke-Sc {
    param([string[]]$ScArgs)
    $out = & sc.exe @ScArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: sc.exe $($ScArgs -join ' ') failed ($LASTEXITCODE):"
        $out | ForEach-Object { Write-Host "    $_" }
        if ($Elevated) { Stop-Transcript | Out-Null }
        exit 1
    }
    $out
}

Write-Host "--- Installing native runner service (root: $RunnerRoot) ---"
Write-Host "    service : $serviceName"
Write-Host "    run as  : $account (delayed-auto)"

# [1/5] create or repair
$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[1/5] service exists (Status=$($existing.Status), StartType=$($existing.StartType))"
    # An existing-but-Disabled service is the silent killer found live
    # (2026-08-20): re-enable in place. sc.exe config, not Set-Service -
    # only sc can express delayed-auto.
    Invoke-Sc @('config', $serviceName, 'start=', 'delayed-auto', 'obj=', $account) | Out-Null
} else {
    Write-Host '[1/5] creating service'
    Invoke-Sc @('create', $serviceName, 'binPath=', "`"$binaryPath`"", `
        'DisplayName=', "`"$displayName`"", 'start=', 'delayed-auto', 'obj=', $account) | Out-Null
    Invoke-Sc @('description', $serviceName, "GitHub Actions Runner ($owner.$runnerName)") | Out-Null
}
# The official config.cmd --runasservice writes a .service marker holding the
# service name; runner self-update and `config.cmd remove` expect it. Writing
# it makes the repo-managed service indistinguishable from an official one.
$serviceMarker = Join-Path $RunnerRoot '.service'
if (-not (Test-Path $serviceMarker)) {
    Set-Content -Path $serviceMarker -Value $serviceName -Encoding ASCII
    Write-Host "      wrote $serviceMarker"
}

# [2/5] failure recovery: restart after 60s, three times, reset counter daily.
# failureflag 1 makes recovery fire on non-zero exit too, not only on a crash.
Invoke-Sc @('failure', $serviceName, 'reset=', '86400', 'actions=', 'restart/60000/restart/60000/restart/60000') | Out-Null
Invoke-Sc @('failureflag', $serviceName, '1') | Out-Null
Write-Host '[2/5] failure recovery: restart x3 after 60s (also on non-zero exit), reset daily'

# [3/5] Machine PATH onion: LocalSystem sees ONLY the Machine PATH.
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$onion = @(
    (Join-Path $env:USERPROFILE 'scoop\shims'),
    (Join-Path $env:USERPROFILE '.bun\bin'),
    (Join-Path $env:LOCALAPPDATA 'mise\shims')
)
$missing = @($onion | Where-Object { $machinePath -notlike "*$_*" })
if ($missing.Count -gt 0) {
    Write-Host '[3/5] WARN: Machine PATH is missing tool entries jobs will need:'
    $missing | ForEach-Object { Write-Host "      $_" }
    Write-Host '      Fix (dry-run first): powershell -ExecutionPolicy Bypass -File scripts/restore_machine_path.ps1'
} else {
    Write-Host '[3/5] Machine PATH entries present (scoop shims / .bun\bin / mise shims).'
    Write-Host '      NOTE: per-user tool state is NOT visible to SYSTEM; proof is the next green job.'
}

# [4/5] _work ownership: trees created by a user-account runner fail git's
# dubious-ownership check once the service runs as SYSTEM. Detect and teach;
# never rewrite ACLs behind the user's back.
$workRoot = Join-Path $RunnerRoot '_work'
if (Test-Path $workRoot) {
    $foreign = @(Get-ChildItem $workRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @('_actions', '_temp', '_tool', '_update') } |
        Where-Object {
            $ownerSid = (Get-Acl $_.FullName).Owner
            $ownerSid -notmatch 'SYSTEM|Administrators'
        })
    if ($foreign.Count -gt 0) {
        Write-Host '[4/5] WARN: _work checkouts owned by a non-SYSTEM account; actions/checkout'
        Write-Host '      will fail git''s "dubious ownership" check under this service. Fix:'
        $foreign | ForEach-Object { Write-Host "      takeown /F `"$($_.FullName)`" /A /R /D Y" }
        Write-Host '      (or: git config --system --add safe.directory <checkout>)'
    } else {
        Write-Host '[4/5] _work ownership compatible with SYSTEM'
    }
} else {
    Write-Host '[4/5] no _work yet (first job creates it as SYSTEM - fine)'
}

# [5/5] start
if ((Get-Service -Name $serviceName).Status -ne 'Running') {
    Write-Host '[5/5] starting service'
    Start-Service -Name $serviceName
} else {
    Write-Host '[5/5] service already running'
}
Start-Sleep -Seconds 3
$svc = Get-Service -Name $serviceName
Write-Host "--- $serviceName is $($svc.Status) (StartType=$($svc.StartType)) ---"
Get-Process -Name 'RunnerService', 'Runner.Listener' -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "    proc: $($_.ProcessName) (pid $($_.Id))" }
Write-Host '    Verify end to end: just status   (and the runner list on GitHub)'
if ($Elevated) { Stop-Transcript | Out-Null }
if ($svc.Status -ne 'Running') { exit 1 }
exit 0
