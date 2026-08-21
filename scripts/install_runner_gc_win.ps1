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
    [string]$TaskName = 'dotfiles-runner-gc',
    [string]$AutostartTaskName = 'dotfiles-wsl-autostart',
    # The distro whose systemd hosts the runner. install_runner_gc.sh forwards
    # its resolved value so bash and PowerShell share one source of truth.
    [string]$Distro = $(if ($env:RUNNER_GC_WSL_DISTRO) { $env:RUNNER_GC_WSL_DISTRO } else { 'Ubuntu' }),
    # Set by the UAC relaunch so the child skips re-elevating and transcripts.
    [switch]$Elevated
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# The elevated child's console vanishes on exit; a transcript is the only
# surviving output (the parent prints and then dumps this path).
if ($Elevated) {
    Start-Transcript -Path (Join-Path $env:TEMP 'runner-gc-install-elevated.log') -Force | Out-Null
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$payload = Join-Path $here 'runner_gc_win.ps1'
if (-not (Test-Path $payload)) {
    throw "payload not found: $payload"
}

# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a BOM-less
# UTF-8 script as ANSI, so any emoji here arrives mojibake in the logs.
Write-Host "--- Installing Windows runner disk GC (retention=$Retention) ---"

# 1. Scheduled Task ----------------------------------------------------------
# Unregister first so re-running never stacks duplicate triggers. A task that
# was registered S4U (elevated) cannot be unregistered from an UNELEVATED
# shell; this installer promises to work without Administrator, so keep the
# existing task and continue with the remaining steps instead of dying here.
$keepGcTask = $false
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    }
    catch {
        Write-Host "[1/3] scheduled task: $TaskName exists but cannot be replaced unelevated; keeping it as-is"
        $keepGcTask = $true
    }
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
if (-not $keepGcTask) {
    $registered = $false
    try {
        $principal = New-ScheduledTaskPrincipal -UserId $me -LogonType S4U -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Settings $settings -Principal $principal `
            -Description 'dotfiles ADR 0035: hourly self-hosted runner disk GC' -ErrorAction Stop | Out-Null
        Write-Host "[1/3] scheduled task: $TaskName (hourly, runs while logged off)"
        $registered = $true
    }
    catch {
        # S4U ("runs while logged off") needs elevation. Try ONE UAC relaunch
        # of this script before settling for Interactive: the elevated child
        # gets the params forwarded explicitly (env/params do not survive UAC)
        # and transcripts to %TEMP% (its console dies on exit). A converged
        # host never prompts again - an existing S4U task cannot even be
        # unregistered unelevated, so the keepGcTask path short-circuits
        # before this point. A declined prompt falls through to Interactive:
        # staying installable unattended beats the better trigger.
        if (-not $Elevated) {
            $gcLog = Join-Path $env:TEMP 'runner-gc-install-elevated.log'
            Write-Host "[1/3] S4U needs elevation; requesting UAC (output lands in: $gcLog)"
            try {
                $psi = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru `
                    -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', `
                    '-File', "`"$($MyInvocation.MyCommand.Path)`"", `
                    '-Retention', $Retention, '-TaskName', $TaskName, `
                    '-AutostartTaskName', $AutostartTaskName, '-Distro', $Distro, '-Elevated'
                if ($psi.ExitCode -eq 0) {
                    Get-Content $gcLog -ErrorAction SilentlyContinue
                    exit 0
                }
                Write-Host "[1/3] elevated install failed ($($psi.ExitCode)); falling back to an interactive trigger"
            }
            catch {
                Write-Host "[1/3] UAC declined; falling back to an interactive trigger"
            }
        }
        else {
            Write-Host "[1/3] S4U registration failed even elevated: $_"
        }
    }
    if (-not $registered) {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Settings $settings `
            -Description 'dotfiles ADR 0035: hourly self-hosted runner disk GC' | Out-Null
        Write-Host "[1/3] scheduled task: $TaskName (hourly, only while signed in)"
    }
}

# 2. WSL autostart at logon ---------------------------------------------------
# After a reboot nothing starts the WSL distro, so the runner service and the
# runner-gc.timer stay down until a human opens a terminal. A logon-trigger
# task closes that gap. Logon, not boot: a boot trigger needs elevation and
# the WSL VM wants a user session anyway. The distro name is baked into the
# command line - a Scheduled Task does not inherit this shell's environment,
# so an env-var default would silently fall back to 'Ubuntu' at logon while
# every interactive run of this installer works.
$autoPayload = Join-Path $here 'wsl_autostart.ps1'
if (-not (Test-Path $autoPayload)) {
    throw "payload not found: $autoPayload"
}

$keepAutoTask = $false
$existingAuto = Get-ScheduledTask -TaskName $AutostartTaskName -ErrorAction SilentlyContinue
if ($existingAuto) {
    try {
        Unregister-ScheduledTask -TaskName $AutostartTaskName -Confirm:$false -ErrorAction Stop
    }
    catch {
        Write-Host "[2/3] scheduled task: $AutostartTaskName exists but cannot be replaced unelevated; keeping it as-is"
        $keepAutoTask = $true
    }
}

$autoAction = New-ScheduledTaskAction `
    -Execute (Get-Command powershell.exe).Source `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Distro {1}' -f $autoPayload, $Distro)
$autoTrigger = New-ScheduledTaskTrigger -AtLogOn -User $me
# IgnoreNew: overlapping firings collapse to one (duplicate-start valve).
# ExecutionTimeLimit 0 (= no limit): the payload ends by BLOCKING as the
# keepalive client that holds the distro open - WSL terminates a distro
# ~1 min after its last client exits, systemd services inside do not count.
# A time limit would kill the task's process tree and the keepalive with it.
$autoSettings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
if (-not $keepAutoTask) {
    Register-ScheduledTask -TaskName $AutostartTaskName -Action $autoAction -Trigger $autoTrigger `
        -Settings $autoSettings `
        -Description 'dotfiles: start the WSL runner distro at logon (reboot recovery)' | Out-Null
    Write-Host "[2/3] scheduled task: $AutostartTaskName (at logon, distro '$Distro')"
}
# Fire once now: the payload attaches the keepalive client immediately, so
# the distro stops depending on an open terminal from this moment on. This
# still proves nothing about REBOOT recovery (the logon trigger has not
# fired) - the real proof is `just status` after the next reboot.
Start-ScheduledTask -TaskName $AutostartTaskName
Write-Host "      fired now (attaches the keepalive); reboot-recovery proof is 'just status' after the next reboot"

# 3. Runner job-completed hook ----------------------------------------------
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
# FORWARD slashes, deliberately: `just` (dotenv-load) walks ancestor
# directories for a `.env`, and every checkout lives under the runner root,
# so this file IS discovered by every just invocation in every job on the
# box - and just's dotenv parser aborts on backslashes in the value (seen
# live 2026-08-21: E#544 `just fmt-check` died on 'error parsing line').
# Windows accepts forward slashes everywhere the value travels (the
# runner's extension validation, PowerShell -File).
$hookCmd = $payload -replace '\\', '/'

$roots = @(
    (Join-Path $env:USERPROFILE 'actions-runner-win'),
    (Join-Path $env:USERPROFILE 'actions-runner'),
    'C:\actions-runner'
) | Where-Object { $_ -and (Test-Path (Join-Path $_ 'config.cmd')) }

if (-not $roots) {
    Write-Host '[3/3] hook: no Windows runner install found; skipped'
}
foreach ($root in $roots) {
    $envFile = Join-Path $root '.env'
    $lines = @()
    if (Test-Path $envFile) {
        $lines = Get-Content $envFile | Where-Object { $_ -notmatch "^$hookKey=" }
    }
    $lines += "$hookKey=$hookCmd"
    [System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "[3/3] hook: $envFile -> $hookKey"
}

Write-Host '--- OK. Installed. Restart the runner to pick up the job hook. ---'
Write-Host "     Verify: Get-ScheduledTask -TaskName $TaskName"
if ($Elevated) { Stop-Transcript | Out-Null }
