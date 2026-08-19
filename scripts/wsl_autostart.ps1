<#
.SYNOPSIS
    Start the WSL distro that hosts the self-hosted runner and keep it alive
    (ADR 0035 family).

.DESCRIPTION
    Fired by the 'dotfiles-wsl-autostart' Scheduled Task at logon. Two
    problems, one mechanism:

      - After a reboot nothing starts the distro, so the runner service and
        the runner-gc.timer stay silent until a human opens a terminal.
      - WSL terminates a distro shortly (~1 min) after its last CLIENT
        exits; systemd services inside do NOT count as clients. Historically
        this box's runner only survived because a terminal happened to stay
        open. A boot-and-exit autostart would therefore protect nothing.

    So this payload boots the distro, verifies the reboot-recovery contract
    (systemd up, a runner unit loaded), and then INTENTIONALLY NEVER EXITS:
    it blocks as a marked keepalive client whose connection holds the distro
    open. The Scheduled Task stays 'Running' - that is the feature. The task
    must carry no ExecutionTimeLimit (a limit kills the process tree, taking
    the keepalive with it).

    Safety valves against duplicate starts:
      A. presence probe for the keepalive marker inside the distro - if a
         prior instance already owns the distro's lifetime, exit 0 instead
         of stacking a second client. The pattern bracket-escapes itself
         ('keepaliv[e]') or it would match its own command line and report
         "already attached" forever.
      B. the runner is only ever launched by its systemd unit, and starting
         an active unit is a no-op - this path cannot double-launch it.
      C. the Scheduled Task registers with -MultipleInstances IgnoreNew, so
         overlapping firings collapse to one.

    The exit code (when it does exit) reflects this script's one job: is the
    distro up, with systemd running and a runner unit loaded. A duplicate
    Runner.Listener (someone also ran run.sh by hand) is a different fact -
    logged as WARN here, turned red by `just status`.
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

# --- observe: is the distro already running? ---------------------------------
# Informational only (the keepalive valve below decides). --quiet drops the
# locale-dependent header and the ' (Default)' suffix, so each line is a bare
# distro name. The match must be exact: 'Ubuntu' is a substring of
# 'Ubuntu-24.04', and a contains-match would mislabel a sibling as the target.
$raw = & $WslExe --list --quiet --running 2>$null
$rc = $LASTEXITCODE
$running = @()
if ($rc -eq 0) { $running = @(Get-CleanLines $raw) }
# rc != 0 means "no running distributions" (or wsl.exe is unhappy); either
# way the right move is to attempt the start (fail-open), not to stay down.
if ($running -contains $Distro) {
    Write-Log "distro '$Distro' is already running"
} else {
    Write-Log "distro '$Distro' is not running; starting it"
}

# --- valve A: is a keepalive already attached? -------------------------------
# This wsl call boots the distro as a side effect when it is down, which is
# fine - that is where this script is headed anyway.
& $WslExe -d $Distro -e sh -c "pgrep -f 'dotfiles-wsl-keepaliv[e]' >/dev/null" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Log "a keepalive client is already attached; nothing to do"
    exit 0
}

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

# --- become the keepalive (intentionally never exits) ------------------------
# The connected client is what keeps the distro (and with it the runner and
# the GC timer) alive. `: marker` keeps the marker visible in the process
# command line for valve A; the loop survives an interrupted sleep.
Write-Log "attaching keepalive client - this task intentionally stays running"
& $WslExe -d $Distro -e sh -c ': dotfiles-wsl-keepalive; while :; do sleep 3600; done'
Write-Log "keepalive exited (wsl.exe exit $LASTEXITCODE) - the distro lost its client"
exit $LASTEXITCODE
