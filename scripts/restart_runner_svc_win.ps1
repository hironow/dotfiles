# Restart the native Windows GitHub Actions runner service (repo-managed
# sibling of install_runner_svc_win.ps1 - same derivation, same UAC
# elevation, same transcript convention). Refuses to kill an in-flight job:
# aborts when Runner.Worker is running (override: -Force).
# ASCII-only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.

[CmdletBinding()]
param(
    [string]$RunnerRoot = '',
    [switch]$Force,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'

if (-not $RunnerRoot) {
    $RunnerRoot = if ($env:RUNNER_WIN_ROOT) { $env:RUNNER_WIN_ROOT }
                  else { Join-Path $env:USERPROFILE 'actions-runner-win' }
}
$logPath = Join-Path $env:TEMP 'runner-svc-restart.log'

$runnerCfgPath = Join-Path $RunnerRoot '.runner'
if (-not (Test-Path $runnerCfgPath)) {
    Write-Host "ERROR: $runnerCfgPath not found - runner not configured; run: just runner-svc-install"
    exit 1
}
$runnerCfg   = Get-Content $runnerCfgPath | ConvertFrom-Json
$owner       = (($runnerCfg.gitHubUrl -replace '^https?://github\.com/', '').TrimEnd('/')) -replace '/', '-'
$serviceName = "actions.runner.$owner.$($runnerCfg.agentName)"

if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: service '$serviceName' is not installed; run: just runner-svc-install"
    exit 1
}

# A restart kills whatever job is executing; refuse while Runner.Worker lives.
if (-not $Force) {
    $worker = Get-Process -Name 'Runner.Worker' -ErrorAction SilentlyContinue
    if ($worker) {
        Write-Host 'ERROR: a job is executing (Runner.Worker is running) - retry when idle,'
        Write-Host '       or override with -Force if you accept killing the job.'
        exit 1
    }
}

$isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Elevating (approve the UAC prompt); output lands in: $logPath"
    $extra = @()
    if ($Force) { $extra += '-Force' }
    try {
        $psi = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru `
            -ArgumentList ((@('-NoProfile', '-ExecutionPolicy', 'Bypass', `
            '-File', "`"$PSCommandPath`"", '-RunnerRoot', "`"$RunnerRoot`"", '-Elevated') + $extra))
    } catch {
        Write-Host 'ERROR: elevation declined or failed - nothing was changed.'
        exit 1
    }
    Get-Content $logPath -ErrorAction SilentlyContinue
    exit $psi.ExitCode
}

if ($Elevated) { Start-Transcript -Path $logPath -Force | Out-Null }

Write-Host "Restarting '$serviceName' ..."
Restart-Service -Name $serviceName -Force
Start-Sleep -Seconds 4
$svc = Get-Service -Name $serviceName
Write-Host "$serviceName is $($svc.Status) (StartType=$($svc.StartType))"
Get-Process -Name 'RunnerService', 'Runner.Listener' -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "    proc: $($_.ProcessName) (pid $($_.Id))" }
if ($Elevated) { Stop-Transcript | Out-Null }
if ($svc.Status -ne 'Running') { exit 1 }
exit 0
