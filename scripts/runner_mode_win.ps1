# ==============================================================================
# Switch the native Windows runner between SERVICE and INTERACTIVE mode
# ------------------------------------------------------------------------------
# Some runner boxes serve GUI e2e (WebView2 windows) and jobs that need the
# user's profile and PATH. A LocalSystem service runs in Session 0, where
# (measured 2026-08-20/21): WebView2 cannot create a window, CodeQL resolves
# its config under systemprofile, and the user's tools are missing from the
# PATH. Those boxes must run the runner INTERACTIVELY in the user's logon
# session. Headless boxes prefer the service (unattended reboot survival).
#
#   -Mode interactive : stop + DISABLE the service (delayed-auto would
#                       resurrect Session 0 at the next reboot - the lived
#                       failure), register a logon task running run.cmd in
#                       the user's interactive session, start it now, and
#                       prove the listener lives outside Session 0.
#   -Mode service     : the inverse - unregister the logon task, re-enable
#                       the service delayed-auto and start it.
#
# Same conventions as install_runner_svc_win.ps1: generic root
# (-RunnerRoot / RUNNER_WIN_ROOT, USERPROFILE default), names derived from
# .runner, UAC self-elevation with explicit arg forwarding + transcript,
# Runner.Worker guard so a mode switch never kills an in-flight job.
# ASCII-only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
# ==============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('interactive', 'service')]
    [string]$Mode,
    [string]$RunnerRoot = '',
    [switch]$Force,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'

if (-not $RunnerRoot) {
    $RunnerRoot = if ($env:RUNNER_WIN_ROOT) { $env:RUNNER_WIN_ROOT }
                  else { Join-Path $env:USERPROFILE 'actions-runner-win' }
}
$taskName = 'dotfiles-runner-interactive'
$logPath = Join-Path $env:TEMP 'runner-mode-win.log'

$runnerCfgPath = Join-Path $RunnerRoot '.runner'
if (-not (Test-Path $runnerCfgPath)) {
    Write-Host "ERROR: $runnerCfgPath not found - runner not configured; nothing to switch."
    exit 1
}
$runCmd = Join-Path $RunnerRoot 'run.cmd'
if (-not (Test-Path $runCmd)) {
    Write-Host "ERROR: $runCmd not found - broken runner install."
    exit 1
}
$runnerCfg   = Get-Content $runnerCfgPath | ConvertFrom-Json
$owner       = (($runnerCfg.gitHubUrl -replace '^https?://github\.com/', '').TrimEnd('/')) -replace '/', '-'
$serviceName = "actions.runner.$owner.$($runnerCfg.agentName)"

# A mode switch stops whatever runner is live; refuse while a job executes.
if (-not $Force) {
    if (Get-Process -Name 'Runner.Worker' -ErrorAction SilentlyContinue) {
        Write-Host 'ERROR: a job is executing (Runner.Worker) - retry when idle, or -Force to kill it.'
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
            '-File', "`"$PSCommandPath`"", '-Mode', $Mode, `
            '-RunnerRoot', "`"$RunnerRoot`"", '-Elevated') + $extra))
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

$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue

if ($Mode -eq 'interactive') {
    Write-Host "--- Switching '$serviceName' to INTERACTIVE mode (root: $RunnerRoot) ---"

    # [1/3] the service must be DISABLED, not just stopped: delayed-auto
    # brings Session 0 back at the next reboot, which is the lived failure.
    if ($svc) {
        if ($svc.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force }
        Invoke-Sc @('config', $serviceName, 'start=', 'disabled') | Out-Null
        Write-Host '[1/3] service stopped + StartType=Disabled (kept installed for the way back)'
    } else {
        Write-Host '[1/3] no service registered - nothing to disable'
    }

    # [2/3] logon task in the USER'S interactive session: GUI-capable, user
    # profile, user PATH. ExecutionTimeLimit zero - Task Scheduler would
    # otherwise kill the runner after its 3-day default.
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction -Execute $runCmd -WorkingDirectory $RunnerRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $me
    $principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description 'dotfiles: GitHub Actions runner, interactive at logon (GUI e2e needs a user session)' | Out-Null
    Write-Host "[2/3] logon task: $taskName (run.cmd as $me, interactive, no time limit)"

    # [2b/3] _work checkouts created by the LocalSystem service are owned by
    # BUILTIN\Administrators; git's dubious-ownership check then refuses them
    # for the interactive user and actions/checkout dies in under a second
    # (lived 2026-08-21: vrt x2). The switch created the mismatch, so the
    # switch repairs it: re-own job dirs to the runner user. takeown WITHOUT
    # /A assigns to the current (elevated) user - exactly the runner account.
    # Runner-internal dirs are skipped by name, never re-owned.
    $workRoot = Join-Path $RunnerRoot '_work'
    if (Test-Path $workRoot) {
        Import-Module Microsoft.PowerShell.Security -ErrorAction SilentlyContinue
        $internal = @('_actions', '_temp', '_tool', '_update', '_PipelineMapping')
        $foreign = @(Get-ChildItem $workRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notin $internal } |
            Where-Object { (Get-Acl $_.FullName).Owner -ne $me })
        foreach ($d in $foreign) {
            Write-Host "      re-owning $($d.Name) (was $((Get-Acl $d.FullName).Owner))"
            & takeown /F "$($d.FullName)" /R /D Y | Out-Null
        }
        if ($foreign.Count -gt 0) {
            Write-Host "[2b/3] re-owned $($foreign.Count) _work checkout(s) to $me (git dubious-ownership)"
        } else {
            Write-Host '[2b/3] _work ownership already matches the runner user'
        }
    }

    # [3/3] start now and PROVE the fix: the listener must live outside
    # Session 0. Stop any previous interactive listener first - a re-run of
    # this switch would otherwise leave two listeners racing for jobs (the
    # Worker guard above already proved no job is executing).
    # NOTE: unattended reboot recovery additionally needs auto-logon for
    # this user; without it the runner waits at the logon screen
    # (deliberate - storing credentials is a human decision).
    Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName $taskName
    $listener = $null
    foreach ($i in 1..15) {
        Start-Sleep -Seconds 2
        $listener = Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) { break }
    }
    if (-not $listener) {
        Write-Host 'ERROR: Runner.Listener did not appear within 30s - inspect the run.cmd window.'
        if ($Elevated) { Stop-Transcript | Out-Null }
        exit 1
    }
    if ($listener.SessionId -eq 0) {
        Write-Host 'ERROR: listener is STILL in Session 0 - the service resurrected it?'
        if ($Elevated) { Stop-Transcript | Out-Null }
        exit 1
    }
    Write-Host "[3/3] Runner.Listener pid $($listener.Id) in session $($listener.SessionId) (interactive - GUI capable)"
    Write-Host '--- OK. Interactive mode active. Unattended reboots need auto-logon for this user. ---'
} else {
    Write-Host "--- Switching '$serviceName' to SERVICE mode (root: $RunnerRoot) ---"

    # [1/3] remove the logon task and any interactive listener it started -
    # otherwise two runners race for jobs.
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -ne 0 } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "[1/3] logon task removed: $taskName"

    # [2/3] re-enable delayed-auto (reboot survival without a logon).
    if (-not $svc) {
        Write-Host 'ERROR: no service registered - run: just runner-svc-install'
        if ($Elevated) { Stop-Transcript | Out-Null }
        exit 1
    }
    Invoke-Sc @('config', $serviceName, 'start=', 'delayed-auto') | Out-Null
    Write-Host '[2/3] service StartType=delayed-auto'

    # [3/3] start
    if ((Get-Service -Name $serviceName).Status -ne 'Running') { Start-Service -Name $serviceName }
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name $serviceName
    Write-Host "[3/3] service is $($svc.Status)"
    Write-Host '--- OK. Service mode active (Session 0 - GUI e2e will NOT work on this box). ---'
    if ($svc.Status -ne 'Running') { if ($Elevated) { Stop-Transcript | Out-Null }; exit 1 }
}

if ($Elevated) { Stop-Transcript | Out-Null }
exit 0
