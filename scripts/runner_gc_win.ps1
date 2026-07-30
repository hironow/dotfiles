<#
.SYNOPSIS
    Disk GC for the Windows-native self-hosted GitHub Actions runner (ADR 0035).

.DESCRIPTION
    The Windows counterpart of scripts/runner_gc.sh. Same time budget: keep
    anything used within -Retention, drop everything older.

    Collects:
      - Docker Desktop containers / images / build cache (when the daemon is up)
      - runner _diag logs, which nothing rotates
      - runner _work/_temp scratch left behind by cancelled jobs

    Installed by scripts/install_runner_gc_win.ps1 as both the runner's
    job-completed hook and an hourly Scheduled Task.

.NOTES
    Never prunes while a job is executing: an in-flight docker build can hold
    cache the age filter would consider cold. The hourly task retries.
#>
[CmdletBinding()]
param(
    # Docker age filter; also the floor for _diag/_temp trimming.
    [string]$Retention = $(if ($env:RUNNER_GC_RETENTION) { $env:RUNNER_GC_RETENTION } else { '2h' }),
    # Keep runner diagnostic logs this many days (they are the only forensic
    # trail for a failed job, so they outlive the docker budget).
    [int]$DiagRetentionDays = 7,
    # Run even when a job is in flight. Only for manual use.
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Write-GcLog {
    param([string]$Message)
    Write-Host ("[runner-gc-win] {0} {1}" -f (Get-Date -Format 'o'), $Message)
}

# --- Job safety -------------------------------------------------------------
# Get-Process matches on the executable name, so unlike the Linux side there is
# no risk of this script matching itself.
if (-not $Force) {
    $worker = Get-Process -Name 'Runner.Worker' -ErrorAction SilentlyContinue
    if ($worker) {
        Write-GcLog 'SKIP: a runner job is executing (Runner.Worker alive)'
        exit 0
    }
}

$free = (Get-PSDrive C).Free / 1GB
Write-GcLog ("start (retention={0}) - C: {1:N1} GB free" -f $Retention, $free)

# --- Docker Desktop ---------------------------------------------------------
# Docker Desktop is frequently stopped on a dev box; a missing daemon is a
# normal state, not an error.
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    & docker info *>$null
    if ($LASTEXITCODE -eq 0) {
        foreach ($step in @(
                @('container', @('container', 'prune', '-f', "--filter=until=$Retention")),
                @('image', @('image', 'prune', '-af', "--filter=until=$Retention")),
                @('build cache', @('builder', 'prune', '-af', "--filter=until=$Retention"))
            )) {
            & docker @($step[1]) *>$null
            Write-GcLog ("docker: pruned {0} older than {1}" -f $step[0], $Retention)
        }
    }
    else {
        Write-GcLog 'docker: daemon not reachable; skipping'
    }
}
else {
    Write-GcLog 'docker: not installed; skipping'
}

# --- Runner working directories --------------------------------------------
$runnerRoots = @(
    (Join-Path $env:USERPROFILE 'actions-runner-win'),
    (Join-Path $env:USERPROFILE 'actions-runner'),
    'C:\actions-runner'
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $runnerRoots) {
    Write-GcLog 'runner: no Windows runner install found; skipping'
}

$diagCutoff = (Get-Date).AddDays(-$DiagRetentionDays)
foreach ($root in $runnerRoots) {
    $diag = Join-Path $root '_diag'
    if (Test-Path $diag) {
        $old = Get-ChildItem $diag -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -lt $diagCutoff }
        if ($old) {
            $mb = [math]::Round((($old | Measure-Object Length -Sum).Sum) / 1MB, 1)
            $old | Remove-Item -Force -ErrorAction SilentlyContinue
            Write-GcLog ("runner: removed {0} _diag logs older than {1}d ({2} MB)" -f $old.Count, $DiagRetentionDays, $mb)
        }
    }

    # _temp is pure scratch - the runner recreates it per job.
    $temp = Join-Path $root '_work\_temp'
    if (Test-Path $temp) {
        Get-ChildItem $temp -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -lt $diagCutoff } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-GcLog 'runner: _work\_temp scratch trimmed'
    }
}

$freeAfter = (Get-PSDrive C).Free / 1GB
Write-GcLog ("done - C: {0:N1} GB free (reclaimed {1:N1} GB)" -f $freeAfter, ($freeAfter - $free))
