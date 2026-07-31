<#
.SYNOPSIS
    Install the disk GC mechanism for the Windows-native runner (ADR 0035).

.DESCRIPTION
    Windows counterpart of scripts/install_runner_gc.sh. Idempotent. Installs
    the same two brakes the WSL side gets:

      1. Scheduled Task 'dotfiles-runner-gc'  - hourly floor (systemd timer analogue)
      2. ACTIONS_RUNNER_HOOK_JOB_COMPLETED    - collects right after each job

    Does NOT require Administrator: the task is registered for the current user
    only, which is also the account the runner runs under.
#>
[CmdletBinding()]
param(
    [string]$Retention = '2h',
    [string]$TaskName = 'dotfiles-runner-gc'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$payload = Join-Path $here 'runner_gc_win.ps1'
if (-not (Test-Path $payload)) {
    throw "payload not found: $payload"
}

# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a BOM-less
# UTF-8 script as ANSI, so any emoji here arrives mojibake in the logs.
Write-Host "--- Installing Windows runner disk GC (retention=$Retention) ---"

# 1. Scheduled Task ----------------------------------------------------------
# Unregister first so re-running never stacks duplicate triggers.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute (Get-Command powershell.exe).Source `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Retention {1}' -f $payload, $Retention)

# RepetitionInterval on a once-trigger is the portable way to say "hourly
# forever" across Windows builds.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(7) `
    -RepetitionInterval (New-TimeSpan -Hours 1)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# S4U ("service for user") runs the task whether or not the account is signed
# in, without storing a password - which is exactly when a CI box most needs
# collecting. Registering it requires elevation though, and staying installable
# unelevated matters more than the better trigger, so fall back to Interactive
# and let `just status` report which one is in force.
$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$registered = $false
try {
    $principal = New-ScheduledTaskPrincipal -UserId $me -LogonType S4U -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal `
        -Description 'dotfiles ADR 0035: hourly self-hosted runner disk GC' -ErrorAction Stop | Out-Null
    Write-Host "[1/2] scheduled task: $TaskName (hourly, runs while logged off)"
    $registered = $true
}
catch {
    Write-Host "[1/2] S4U needs elevation; falling back to an interactive trigger"
}
if (-not $registered) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings `
        -Description 'dotfiles ADR 0035: hourly self-hosted runner disk GC' | Out-Null
    Write-Host "[1/2] scheduled task: $TaskName (hourly, only while signed in)"
}

# 2. Runner job-completed hook ----------------------------------------------
# The runner reads .env from its install dir at service start. Upsert the key
# so repeated runs never duplicate the line, and keep the file ASCII/UTF8
# without a BOM - the runner's parser chokes on a BOM.
$hookKey = 'ACTIONS_RUNNER_HOOK_JOB_COMPLETED'
# The value must be a PATH to a script, not a command line: the runner
# validates the extension and rejects anything else with
#   ArgumentException: <value> is not a valid path to a script.
# A `powershell.exe ... -File <script>` wrapper therefore fails on every job
# while reading perfectly in `.env`. Retention comes from the environment
# default instead of an argument.
$hookCmd = $payload

$roots = @(
    (Join-Path $env:USERPROFILE 'actions-runner-win'),
    (Join-Path $env:USERPROFILE 'actions-runner'),
    'C:\actions-runner'
) | Where-Object { $_ -and (Test-Path (Join-Path $_ 'config.cmd')) }

if (-not $roots) {
    Write-Host '[2/2] hook: no Windows runner install found; skipped'
}
foreach ($root in $roots) {
    $envFile = Join-Path $root '.env'
    $lines = @()
    if (Test-Path $envFile) {
        $lines = Get-Content $envFile | Where-Object { $_ -notmatch "^$hookKey=" }
    }
    $lines += "$hookKey=$hookCmd"
    [System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "[2/2] hook: $envFile -> $hookKey"
}

Write-Host '--- OK. Installed. Restart the runner to pick up the job hook. ---'
Write-Host "     Verify: Get-ScheduledTask -TaskName $TaskName"
