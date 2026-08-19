<#
.SYNOPSIS
    Start the WSL distro that hosts the self-hosted runner (ADR 0035 family).

.DESCRIPTION
    Fired by the 'dotfiles-wsl-autostart' Scheduled Task at logon. After a
    reboot nothing else starts the distro, so the runner service and the
    runner-gc.timer stay silent until a human opens a terminal. This payload
    boots the distro once; systemd inside it brings up every enabled unit.

    Safety valves against duplicate starts:
      A. exact-match check against `wsl --list --quiet --running` - if the
         distro is already up, exit 0 without touching WSL at all.
      B. the runner is only ever launched by its systemd unit, and starting
         an active unit is a no-op - this path cannot double-launch it.
      C. the Scheduled Task registers with -MultipleInstances IgnoreNew, so
         overlapping firings collapse to one.

    The exit code reflects this script's one job: is the distro up, with
    systemd running and a runner unit loaded. A duplicate Runner.Listener
    (someone also ran run.sh by hand) is a different fact - logged as WARN
    here, turned red by `just status`.
#>
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu',
    # Injectable so tests can substitute a stub for the real wsl.exe.
    [string]$WslExe = 'wsl.exe'
)

Set-StrictMode -Version Latest
# 'Continue', not 'Stop': native exit codes are data here. `wsl --list
# --running` exits non-zero when nothing runs - the exact case this script
# exists for - and pwsh 7 would turn that into a terminating error where
# powershell.exe 5.1 does not.
$ErrorActionPreference = 'Continue'

# wsl.exe emits UTF-16LE by default; WSL_UTF8=1 makes it UTF-8 so the output
# parses here and stays readable in the Scheduled Task log. The NUL stripping
# below remains as a fallback for hosts that ignore the variable.
$env:WSL_UTF8 = '1'

# NOTE: keep this file ASCII-only. powershell.exe 5.1 reads a BOM-less UTF-8
# script as ANSI, so any emoji here arrives mojibake in the task log.
function Write-Log([string]$Message) {
    Write-Host ('[wsl-autostart] {0} {1}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'), $Message)
}

function Get-CleanLines($Raw) {
    @($Raw) | ForEach-Object { ("$_" -replace "`0", '').Trim() } | Where-Object { $_ }
}

# --- valve A: already running? ----------------------------------------------
# --quiet drops the locale-dependent header and the ' (Default)' suffix, so
# each line is a bare distro name. The match must be exact: 'Ubuntu' is a
# substring of 'Ubuntu-24.04', and a contains-match would report "already
# running" while the target distro is down - silencing the very mechanism
# this valve guards.
$raw = & $WslExe --list --quiet --running 2>$null
$rc = $LASTEXITCODE
$running = @()
if ($rc -eq 0) { $running = @(Get-CleanLines $raw) }
# rc != 0 means "no running distributions" (or wsl.exe is unhappy); either
# way the right move is to attempt the start (fail-open), not to stay down.
if ($running -contains $Distro) {
    Write-Log "distro '$Distro' is already running; nothing to do"
    exit 0
}

Write-Log "starting distro '$Distro'"
& $WslExe -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "FAIL: could not start distro '$Distro' (wsl.exe exit $LASTEXITCODE)"
    exit 1
}

# --- contract: systemd must actually be up -----------------------------------
# Without `[boot] systemd=true` in /etc/wsl.conf the distro starts, `true`
# runs, and no service ever comes up while every log line stays green. Make
# that a hard failure. is-system-running reports 'starting' during boot, so
# poll briefly before judging.
$state = ''
foreach ($attempt in 1..12) {
    $state = (Get-CleanLines (& $WslExe -d $Distro -u root -e systemctl is-system-running 2>$null)) |
        Select-Object -First 1
    if ($state -eq 'running' -or $state -eq 'degraded') { break }
    Start-Sleep -Seconds 5
}
if ($state -ne 'running' -and $state -ne 'degraded') {
    Write-Log "FAIL: systemd is not up in '$Distro' (state: '$state') - run: just wsl-conf, then wsl --shutdown"
    exit 1
}

# --- contract: a runner unit must be loaded ----------------------------------
# `systemctl is-active 'actions.runner.*'` exits 0 when NO unit matches the
# glob, so count loaded units explicitly instead of trusting a zero exit.
$units = @(Get-CleanLines (& $WslExe -d $Distro -u root -e systemctl list-units --type=service --all --no-legend --plain 'actions.runner.*' 2>$null))
if ($units.Count -eq 0) {
    Write-Log "FAIL: no actions.runner.* service unit is loaded in '$Distro'"
    exit 1
}
Write-Log ("runner unit(s) loaded: {0}" -f $units.Count)

# --- duplicate listener: surface, do not fix, do not fail --------------------
$listeners = (Get-CleanLines (& $WslExe -d $Distro -u root -e sh -c 'pgrep -cx Runner.Listener || true' 2>$null)) |
    Select-Object -First 1
if ([int]"0$listeners" -gt 1) {
    Write-Log "WARN: $listeners Runner.Listener processes - a runner was also launched outside systemd"
}

Write-Log "done - distro '$Distro' is up"
exit 0
