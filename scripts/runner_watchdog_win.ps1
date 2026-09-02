# ==============================================================================
# Watchdog for the INTERACTIVE Windows runner (dotfiles-runner-interactive)
# ------------------------------------------------------------------------------
# Third live report (2026-09-03, gpu-win): the interactive listener died
# mid-day with no shutdown line in _diag, no Application event, and Task
# Scheduler history disabled - and nothing restarted it until the next logon.
# The logon task has no restart policy (run.cmd exits 0 on "terminated"), so
# the box sat OFFLINE for 34 minutes while jobs queued behind it.
#
# This script is the one action a watchdog is allowed: if no Runner.Listener
# is alive, re-fire the logon task. It never kills anything (a watchdog that
# kills is a second way to lose an in-flight job), and every restart leaves a
# dated line in %TEMP%\runner-watchdog-win.log so the NEXT death has a time.
#
#   (no switch)  : the check. Meant to be run by the task every N minutes.
#   -Install     : register the repeating task 'dotfiles-runner-watchdog'
#                  (at logon + every -IntervalMinutes, IgnoreNew), remove the
#                  legacy Startup .lnk that raced the logon task, and try to
#                  enable Task Scheduler history (needs admin; warns otherwise).
#   -Uninstall   : remove the task (and the installed copy).
#
# The task runs a COPY at %LOCALAPPDATA%\dotfiles\runner_watchdog_win.ps1, not
# this working-tree file: lived 2026-09-03 02:18/02:23 - the task pointed at the
# repo path, a branch switch removed the file, and two ticks exited 0xFFFD0000
# (powershell: -File not found) with no log line. Re-run -Install after editing.
#
# Same conventions as runner_mode_win.ps1: generic root (-RunnerRoot /
# RUNNER_WIN_ROOT, USERPROFILE default), no hard-coded user, ASCII-only
# (PowerShell 5.1 reads BOM-less UTF-8 as ANSI). Unelevated on purpose: a
# per-user task is the user's to register.
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [int]$IntervalMinutes = 5,
    [string]$RunnerRoot = ''
)

$ErrorActionPreference = 'Stop'

if (-not $RunnerRoot) {
    $RunnerRoot = if ($env:RUNNER_WIN_ROOT) { $env:RUNNER_WIN_ROOT }
                  else { Join-Path $env:USERPROFILE 'actions-runner-win' }
}
$watchTask = 'dotfiles-runner-watchdog'
$runnerTask = 'dotfiles-runner-interactive'
$logPath = Join-Path $env:TEMP 'runner-watchdog-win.log'
$installDir = Join-Path $env:LOCALAPPDATA 'dotfiles'
$installed = Join-Path $installDir 'runner_watchdog_win.ps1'
$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name

function Write-WdLog {
    param([string]$Message)
    # Keep the file small: it is a heartbeat, not an archive.
    if ((Test-Path $logPath) -and ((Get-Item $logPath).Length -gt 1MB)) {
        Get-Content $logPath -Tail 200 | Set-Content $logPath
    }
    ('{0} {1}' -f (Get-Date -Format 'o'), $Message) | Add-Content $logPath
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $watchTask -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $installed -Force -ErrorAction SilentlyContinue
    Write-Host "watchdog task removed: $watchTask (+ copy $installed)"
    exit 0
}

if ($Install) {
    if (-not (Test-Path (Join-Path $RunnerRoot 'run.cmd'))) {
        Write-Host "ERROR: $RunnerRoot\run.cmd not found - not a runner root."
        exit 1
    }
    if (-not (Get-ScheduledTask -TaskName $runnerTask -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: $runnerTask is not registered - run: just runner-mode-interactive"
        exit 1
    }

    # [1/4] a copy outside the working tree. The task must not depend on which
    # branch the repo happens to be on (see header: two silent ticks, 2026-09-03).
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    $self = [IO.Path]::GetFullPath($PSCommandPath)
    if ($self -ine [IO.Path]::GetFullPath($installed)) {
        Copy-Item -LiteralPath $self -Destination $installed -Force
    }
    Write-Host "[1/4] installed copy: $installed (the task runs this; re-run -Install after editing the repo file)"

    # [2/4] the task. Interactive logon type: it only makes sense while the user
    # is logged on (the listener it restarts needs that session anyway).
    Unregister-ScheduledTask -TaskName $watchTask -Confirm:$false -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction `
        -Execute (Get-Command powershell.exe).Source `
        -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -RunnerRoot "{1}"' -f $installed, $RunnerRoot)
    $every = New-TimeSpan -Minutes $IntervalMinutes
    $triggers = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $me),
        # 10 years, not [TimeSpan]::MaxValue: Task Scheduler rejects MaxValue
        # as out of range (HRESULT 0x80041318, lived 2026-09-03 on PS 5.1).
        (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval $every -RepetitionDuration (New-TimeSpan -Days 3650))
    )
    $principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $watchTask -Action $action -Trigger $triggers `
        -Principal $principal -Settings $settings `
        -Description ('dotfiles: restart the interactive runner task when Runner.Listener is gone (every {0} min)' -f $IntervalMinutes) | Out-Null
    Write-Host "[2/4] watchdog task: $watchTask (at logon + every $IntervalMinutes min, re-fires $runnerTask)"

    # [3/4] the legacy start path. The pre-repo script dropped a Startup
    # shortcut to run.cmd; with the logon task that is TWO starts per logon and
    # the loser loops on "A session for this runner already exists"
    # (lived 2026-08-30). One start path: the task.
    $startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
    $shell = New-Object -ComObject WScript.Shell
    $legacy = @(Get-ChildItem -Path $startup -Filter '*.lnk' -ErrorAction SilentlyContinue |
        Where-Object {
            $sc = $shell.CreateShortcut($_.FullName)
            $sc.TargetPath -like '*run.cmd' -and $sc.TargetPath -like ('{0}*' -f $RunnerRoot)
        })
    foreach ($l in $legacy) {
        Remove-Item -LiteralPath $l.FullName -Force
        Write-Host "[3/4] removed legacy Startup shortcut: $($l.Name) (second start path -> session conflict)"
    }
    if ($legacy.Count -eq 0) { Write-Host '[3/4] no legacy Startup shortcut to remove' }

    # [4/4] history. Disabled by default on Windows; without it a task that
    # ends leaves no trace. Needs admin - the elevated mode switch does it
    # for real; here we only try and say so.
    $hist = 'could not enable (needs admin - just runner-mode-interactive does it)'
    try {
        $null = & wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true 2>&1
        if ($LASTEXITCODE -eq 0) { $hist = 'enabled' }
    } catch { }
    Write-Host "[4/4] Task Scheduler history: $hist"
    Write-WdLog ("install by {0}: every {1} min, runs {2}, log {3}" -f $me, $IntervalMinutes, $installed, $logPath)
    exit 0
}

# --- the check --------------------------------------------------------------
$listener = Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-WdLog ("ok: Runner.Listener pid {0} session {1}" -f $listener.Id, $listener.SessionId)
    exit 0
}
$task = Get-ScheduledTask -TaskName $runnerTask -ErrorAction SilentlyContinue
if (-not $task) {
    # Service mode (or never installed): not ours to start.
    Write-WdLog ("idle: no Runner.Listener and no {0} task - nothing to restart" -f $runnerTask)
    exit 0
}
Write-WdLog ("RESTART: no Runner.Listener; task {0} state={1} - firing" -f $runnerTask, $task.State)
Start-ScheduledTask -TaskName $runnerTask
$back = $null
foreach ($i in 1..15) {
    Start-Sleep -Seconds 2
    $back = Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($back) { break }
}
if ($back) {
    Write-WdLog ("RESTART ok: Runner.Listener pid {0} session {1}" -f $back.Id, $back.SessionId)
    exit 0
}
Write-WdLog 'RESTART FAILED: Runner.Listener did not appear within 30s (inspect run.cmd / _diag)'
exit 1
