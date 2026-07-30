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
      - runner _work/<repo> workspaces idle past -Retention
      - superseded runner versions (bin.*/externals.*) and installer archives

    Installed by scripts/install_runner_gc_win.ps1 as both the runner's
    job-completed hook and an hourly Scheduled Task.

.NOTES
    Never prunes while a job is executing: an in-flight docker build can hold
    cache the age filter would consider cold. The hourly task retries.

    Workspaces are aged on a marker file, never on the directory timestamp:
    Windows does not bump a directory's LastWriteTime when a nested file
    changes, so a checkout rebuilt minutes ago can still read months old.
#>
[CmdletBinding()]
param(
    # Docker age filter; also the budget for workspace and _temp trimming.
    [string]$Retention = $(if ($env:RUNNER_GC_RETENTION) { $env:RUNNER_GC_RETENTION } else { '2h' }),
    # Keep runner diagnostic logs this many days (they are the only forensic
    # trail for a failed job, so they outlive the docker budget).
    [int]$DiagRetentionDays = 7,
    # Sweep this install only instead of probing the usual locations. The tests
    # point it at a synthetic runner root.
    [string]$RunnerRoot,
    # Leave the Docker daemon alone; the native runner's growth is on disk.
    [switch]$SkipDocker,
    # Report what would be collected and delete nothing. Sweeping workspaces is
    # the one irreversible thing this script does, so it earns a rehearsal.
    [switch]$DryRun,
    # Run even when a job is in flight. Only for manual use.
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Write-GcLog {
    param([string]$Message)
    Write-Host ("[runner-gc-win] {0} {1}" -f (Get-Date -Format 'o'), $Message)
}

# Stamped into a workspace whenever a job finishes there. See .NOTES.
$Marker = '.runner-gc-last-used'

# The runner owns these; only the sibling directories are repo workspaces.
# Matching on a leading underscore instead would permanently exclude a repo
# actually named `_foo`.
$RunnerManaged = @('_actions', '_diag', '_PipelineMapping', '_temp', '_tool', '_update')

function ConvertTo-Hours {
    <# Read docker's own age syntax (2h, 90m, 7d) as a number of hours. #>
    param([string]$Duration)
    if ($Duration -match '^\s*([0-9]+(?:\.[0-9]+)?)([smhd])\s*$') {
        $value = [double]$Matches[1]
        switch ($Matches[2]) {
            's' { return $value / 3600 }
            'm' { return $value / 60 }
            'd' { return $value * 24 }
            default { return $value }
        }
    }
    # Never widen the window to "everything" because the input was odd.
    Write-GcLog ("retention '{0}' not understood; using 2h" -f $Duration)
    return 2.0
}

function Remove-Tree {
    <# Delete a workspace whole. Three things defeat a plain Remove-Item here:
       junctions (Windows PowerShell recurses *through* them and takes the
       target's contents with it), read-only files (.git/objects), and paths
       past MAX_PATH (node_modules nests deep enough on its own). #>
    param([string]$Path)

    if ($DryRun) {
        Write-GcLog ("DRY-RUN: would remove {0}" -f $Path)
        return
    }

    Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } |
        Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object {
            try {
                if ($_.PSIsContainer) { [IO.Directory]::Delete($_.FullName, $false) }
                else { [IO.File]::Delete($_.FullName) }
            }
            catch { Write-GcLog ("runner: could not detach link {0}" -f $_.FullName) }
        }

    Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $_.IsReadOnly } |
        ForEach-Object { try { $_.IsReadOnly = $false } catch { } }

    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue

    if (Test-Path -LiteralPath $Path) {
        # robocopy speaks the long-path API natively; mirroring an empty
        # directory over the leftovers flattens what Remove-Item could not
        # reach. /XJ so it cannot cross a junction out of the workspace.
        $empty = Join-Path ([IO.Path]::GetTempPath()) ('rgc-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $empty -Force | Out-Null
        & robocopy $empty $Path /MIR /XJ /R:0 /W:0 /NFL /NDL /NJH /NJS /NP *>$null
        Remove-Item -LiteralPath $empty -Force -Recurse -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path -LiteralPath $Path) {
        Write-GcLog ("runner: FAILED to remove {0} (in use?)" -f $Path)
    }
}

# --- Job safety -------------------------------------------------------------
# Get-Process matches on the executable name, so unlike the Linux side there is
# no risk of this script matching itself.
# The job-completed hook is invoked *by* Runner.Worker, so the worker of the job
# we are collecting after is always alive and always our own ancestor. Counting
# it would make the hook skip every single time; only a worker outside our
# ancestry belongs to a concurrent job.
function Get-AncestorProcessId {
    $ids = @()
    $walk = $PID
    while ($walk) {
        $ids += $walk
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$walk" -ErrorAction SilentlyContinue
        if (-not $proc) { break }
        $walk = $proc.ParentProcessId
        if ($ids -contains $walk) { break }   # defensive: never loop on a cycle
    }
    return $ids
}

if (-not $Force) {
    $ancestors = Get-AncestorProcessId
    # @() so a single match does not unroll to a bare object under StrictMode.
    $foreign = @(
        Get-Process -Name 'Runner.Worker' -ErrorAction SilentlyContinue |
            Where-Object { $ancestors -notcontains $_.Id }
    )
    if ($foreign.Count -gt 0) {
        Write-GcLog 'SKIP: another runner job is executing (Runner.Worker alive)'
        exit 0
    }
}

$free = (Get-PSDrive C).Free / 1GB
Write-GcLog ("start (retention={0}) - C: {1:N1} GB free" -f $Retention, $free)

# --- Docker Desktop ---------------------------------------------------------
# Docker Desktop is frequently stopped on a dev box; a missing daemon is a
# normal state, not an error.
$docker = if ($SkipDocker) { $null } else { Get-Command docker -ErrorAction SilentlyContinue }
if ($docker) {
    & docker info *>$null
    if ($LASTEXITCODE -eq 0) {
        foreach ($step in @(
                @('container', @('container', 'prune', '-f', "--filter=until=$Retention")),
                @('image', @('image', 'prune', '-af', "--filter=until=$Retention")),
                @('build cache', @('builder', 'prune', '-af', "--filter=until=$Retention"))
            )) {
            if ($DryRun) {
                Write-GcLog ("DRY-RUN: would prune docker {0} older than {1}" -f $step[0], $Retention)
                continue
            }
            & docker @($step[1]) *>$null
            Write-GcLog ("docker: pruned {0} older than {1}" -f $step[0], $Retention)
        }
    }
    else {
        Write-GcLog 'docker: daemon not reachable; skipping'
    }
}
elseif ($SkipDocker) {
    Write-GcLog 'docker: -SkipDocker requested; skipping'
}
else {
    Write-GcLog 'docker: not installed; skipping'
}

# --- Runner working directories --------------------------------------------
$runnerRoots = @(
    if ($RunnerRoot) { $RunnerRoot }
    else {
        (Join-Path $env:USERPROFILE 'actions-runner-win')
        (Join-Path $env:USERPROFILE 'actions-runner')
        'C:\actions-runner'
    }
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $runnerRoots) {
    Write-GcLog 'runner: no Windows runner install found; skipping'
}

$diagCutoff = (Get-Date).AddDays(-$DiagRetentionDays)
foreach ($root in $runnerRoots) {
    $diag = Join-Path $root '_diag'
    if (Test-Path $diag) {
        # Wrapped in @() because runner_gc.sh drives this through
        # powershell.exe (5.1), where a single match comes back as a bare
        # FileInfo with no .Count under StrictMode - and the trim then throws
        # on the log line below. pwsh 7 papers over it, so the tests cannot
        # see this one.
        $old = @(Get-ChildItem $diag -File -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt $diagCutoff })
        if ($old.Count) {
            $mb = [math]::Round((($old | Measure-Object Length -Sum).Sum) / 1MB, 1)
            if ($DryRun) {
                Write-GcLog ("DRY-RUN: would remove {0} _diag logs older than {1}d ({2} MB)" -f $old.Count, $DiagRetentionDays, $mb)
            }
            else {
                $old | Remove-Item -Force -ErrorAction SilentlyContinue
                Write-GcLog ("runner: removed {0} _diag logs older than {1}d ({2} MB)" -f $old.Count, $DiagRetentionDays, $mb)
            }
        }
    }

    # _temp is pure scratch - the runner recreates it per job.
    $temp = Join-Path $root '_work\_temp'
    if (Test-Path $temp) {
        $scratch = @(Get-ChildItem $temp -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt $diagCutoff })
        if ($DryRun) {
            if ($scratch.Count) {
                Write-GcLog ("DRY-RUN: would trim {0} _work\_temp entries" -f $scratch.Count)
            }
        }
        else {
            $scratch | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            Write-GcLog 'runner: _work\_temp scratch trimmed'
        }
    }

    # --- Workspaces ---------------------------------------------------------
    # Where the growth actually is: `_work/<repo>` holds the checkout plus
    # everything the build wrote into it (a single Rust target/ reached 3.7 GB
    # on this host, against 12 KB of _temp). Nothing rotates it, and the runner
    # is happy to re-clone.
    #
    # Guarded by .runner because this deletes whole trees: without that file
    # the path is not a runner install and we must not touch it.
    if (-not (Test-Path (Join-Path $root '.runner'))) {
        Write-GcLog ("runner: {0} has no .runner file; workspace sweep skipped" -f $root)
        continue
    }

    $work = Join-Path $root '_work'

    # Paths the runner is using right now. Excluded whatever the ageing says -
    # a hook firing between steps must never delete the job's own checkout.
    $live = @()
    foreach ($candidate in @($env:RUNNER_WORKSPACE, $env:GITHUB_WORKSPACE)) {
        if (-not $candidate) { continue }
        try { $live += (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path }
        catch { }
    }

    # Stamp the workspace of the job that just finished, so the next sweep ages
    # it from now rather than from whenever the directory was created.
    if ($env:GITHUB_REPOSITORY) {
        $finished = Join-Path $work (($env:GITHUB_REPOSITORY -split '/')[-1])
        if (Test-Path -LiteralPath $finished) {
            # Protected either way, so a rehearsal reports the same set a real
            # run would collect; only the write itself is held back.
            $live += (Resolve-Path -LiteralPath $finished).Path
            if (-not $DryRun) {
                $stamp = Join-Path $finished $Marker
                try {
                    if (Test-Path -LiteralPath $stamp) {
                        (Get-Item -LiteralPath $stamp -Force).LastWriteTime = Get-Date
                    }
                    else {
                        New-Item -ItemType File -Path $stamp -Force | Out-Null
                    }
                }
                catch { Write-GcLog ("runner: could not stamp {0}" -f $stamp) }
            }
        }
    }

    $workCutoff = (Get-Date).AddHours(-(ConvertTo-Hours $Retention))
    foreach ($ws in @(Get-ChildItem -LiteralPath $work -Directory -Force -ErrorAction SilentlyContinue)) {
        if ($RunnerManaged -contains $ws.Name) { continue }

        $inUse = $false
        foreach ($path in $live) {
            if ($path -eq $ws.FullName -or $path.StartsWith(
                    $ws.FullName + [IO.Path]::DirectorySeparatorChar,
                    [StringComparison]::OrdinalIgnoreCase)) {
                $inUse = $true
            }
        }
        if ($inUse) { continue }

        # The marker is the only honest "last used" signal; the directory
        # timestamp is a fallback for workspaces predating this GC.
        $stamp = Join-Path $ws.FullName $Marker
        $lastUsed = if (Test-Path -LiteralPath $stamp) {
            (Get-Item -LiteralPath $stamp -Force).LastWriteTime
        }
        else { $ws.LastWriteTime }

        if ($lastUsed -lt $workCutoff) {
            Write-GcLog ("runner: collecting workspace {0} (idle since {1:yyyy-MM-dd HH:mm})" -f $ws.Name, $lastUsed)
            Remove-Tree $ws.FullName
        }
    }

    # --- Superseded runner versions -----------------------------------------
    # These get a 24 h floor of their own regardless of -Retention: the runner
    # stages a self-update into _work/_update and only then swings the
    # bin/externals links over, so a 2 h window could catch an update mid-flight.
    $staleCutoff = (Get-Date).AddHours(-24)

    $update = Join-Path $work '_update'
    if ((Test-Path -LiteralPath $update) -and
        ((Get-Item -LiteralPath $update -Force).LastWriteTime -lt $staleCutoff)) {
        Write-GcLog 'runner: collecting stale _update staging'
        Remove-Tree $update
    }

    foreach ($name in @('bin', 'externals')) {
        $link = Join-Path $root $name
        if (-not (Test-Path -LiteralPath $link)) { continue }
        $item = Get-Item -LiteralPath $link -Force
        if (-not $item.LinkType) {
            # A plain install keeps the runner *in* bin/, so a bin.* sibling
            # would be the live runner rather than a leftover. Leave it.
            continue
        }
        $target = @($item.Target)[0]
        if (-not $target) { continue }
        $current = Split-Path -Leaf $target
        Get-ChildItem -LiteralPath $root -Directory -Force -Filter "$name.*" -ErrorAction SilentlyContinue |
            Where-Object {
                # Windows reads a trailing `.*` as "extension optional", so
                # this filter also returns the live `bin` link - whose name
                # never equals the resolved target, so the check below would
                # wave it through and leave a runner that cannot start.
                $_.Name -ne $name -and
                -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
                $_.Name -ne $current -and
                $_.LastWriteTime -lt $staleCutoff
            } |
            ForEach-Object {
                Write-GcLog ("runner: collecting superseded {0}" -f $_.Name)
                Remove-Tree $_.FullName
            }
    }

    Get-ChildItem -LiteralPath $root -File -Force -Filter 'actions-runner-win-*.zip' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $staleCutoff } |
        ForEach-Object {
            Write-GcLog ("runner: collecting installer archive {0}" -f $_.Name)
            Remove-Tree $_.FullName
        }
}

$freeAfter = (Get-PSDrive C).Free / 1GB
Write-GcLog ("done - C: {0:N1} GB free (reclaimed {1:N1} GB)" -f $freeAfter, ($freeAfter - $free))
