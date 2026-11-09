<#
.SYNOPSIS
    Disk GC for the Windows-native self-hosted GitHub Actions runner (ADR 0035).

.DESCRIPTION
    The Windows counterpart of scripts/runner_gc.sh. Young containers/images
    survive based on Created, not last-use time.
    Build/mount cache is deliberately retained (ADR 0067).

    Collects:
      - Podman stopped containers and individually selected aged images
      - runner _diag logs, which nothing rotates
      - runner _work/_temp scratch left behind by cancelled jobs
      - runner _work/<repo> workspaces idle past -Retention
      - superseded runner versions (bin.*/externals.*) and installer archives

    Installed by scripts/install_runner_gc_win.ps1 as both the runner's
    job-completed hook and an hourly Scheduled Task.

.NOTES
    Backs off for foreign jobs, excluding its own worker ancestry. This is a
    point-in-time check, not a global lock against third-party operations.

    Workspaces are aged on a marker file, never on the directory timestamp:
    Windows does not bump a directory's LastWriteTime when a nested file
    changes, so a checkout rebuilt minutes ago can still read months old.
#>
[CmdletBinding()]
param(
    # Podman creation-age budget; also used for workspace retention.
    [string]$Retention = $(if ($env:RUNNER_GC_RETENTION) { $env:RUNNER_GC_RETENTION } else { '2h' }),
    # Keep runner diagnostic logs this many days (they are the only forensic
    # trail for a failed job, so they outlive the podman budget).
    [int]$DiagRetentionDays = 7,
    # Sweep this install only instead of probing the usual locations. The tests
    # point it at a synthetic runner root.
    [string]$RunnerRoot,
    # Leave the Podman daemon alone; the native runner's growth is on disk.
    [Alias("SkipDocker")]
    [switch]$SkipPodman,
    # Run only the engine leg; never expand this into filesystem janitors.
    [switch]$PodmanOnly,
    [string]$KeepTagPrefix = $(if ($env:RUNNER_GC_KEEP_TAG_PREFIX) { $env:RUNNER_GC_KEEP_TAG_PREFIX } else { 'keep/' }),
    # Report what would be collected and delete nothing. Sweeping workspaces is
    # the one irreversible thing this script does, so it earns a rehearsal.
    [switch]$DryRun,
    # Run even when a job is in flight. Only for manual use.
    [switch]$Force,
    # Watchdog budget for every CLI call, including reads. Retains the bounded
    # termination guard from the previous engine; no availability assumption.
    [Alias("DockerTimeoutSec")]
    [ValidateRange(1, 1800)]
    [int]$PodmanTimeoutSec = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Write-GcLog {
    param([string]$Message)
    Write-Host ("[runner-gc-win] {0} {1}" -f (Get-Date -Format 'o'), $Message)
}

function Invoke-PodmanGuarded {
    <# Every engine call is bounded, including enumeration and inspection.
       Output is data, never mixed with watchdog logs. #>
    param([string[]]$PodmanArgs, [int]$TimeoutSec)
    $stdout = [IO.Path]::GetTempFileName()
    $stderr = [IO.Path]::GetTempFileName()
    $proc = $null
    try {
        $proc = Start-Process -FilePath 'podman' -ArgumentList $PodmanArgs `
            -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
            Write-GcLog ("podman: {0} timed out after {1}s; killing it" -f ($PodmanArgs -join ' '), $TimeoutSec)
            & taskkill /PID $proc.Id /T /F *>$null
            return $null
        }
        # Refresh avoids a stale/null ExitCode from Start-Process on Windows.
        $proc.Refresh()
        return @{ ExitCode = $proc.ExitCode; Output = [IO.File]::ReadAllText($stdout) }
    }
    catch { return $null }
    finally {
        if ($proc) { $proc.Dispose() }
        Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Get-PodmanJson {
    param([string[]]$PodmanArgs, [switch]$Inspection)
    $result = Invoke-PodmanGuarded -PodmanArgs $PodmanArgs -TimeoutSec $PodmanTimeoutSec
    if ($null -eq $result -or $result.ExitCode -ne 0) { throw 'Podman query failed' }
    # ConvertFrom-Json 5.1 unwraps arrays on the pipeline. Check the wire shape
    # before that loses the distinction between [one object] and one object.
    if ($Inspection -and -not $result.Output.TrimStart().StartsWith('[')) { throw 'Inspection array required' }
    # Windows PowerShell 5.1, which runs this GC, keeps JSON date strings as
    # strings. PowerShell 7 turns the ones it reads as dates into DateTime,
    # which the Created checks reject, so the item is kept. 7.5+ keeps them as
    # strings with -DateKind String; 7.0-7.4 has no such switch and is not
    # supported. The cmdlet is asked module-qualified, so that a function
    # named Get-Command cannot answer for it.
    $convert = @{ InputObject = $result.Output; ErrorAction = 'Stop' }
    $cmdlet = Microsoft.PowerShell.Core\Get-Command -Name ConvertFrom-Json -CommandType Cmdlet -ErrorAction Stop
    if ($cmdlet.Parameters.ContainsKey('DateKind')) { $convert.DateKind = 'String' }
    return Microsoft.PowerShell.Utility\ConvertFrom-Json @convert
}

function ConvertTo-PodmanImageId {
    param([object]$Value)
    if ($Value -isnot [string] -or $Value -cnotmatch '\A(?:sha256:)?([a-f0-9]{64})\z') {
        throw 'Invalid full image ID'
    }
    return $Matches[1]
}

function Get-PodmanCutoff {
    # Decimal strings are bounded before integral conversion/multiplication.
    # AddSeconds already failed closed on range exceptions; no PS overflow
    # deletion was demonstrated. This also rejects retention before Unix epoch.
    if ($Retention -cnotmatch '\A([0-9]+)([smhd]?)\z') { throw 'Invalid Podman retention' }
    $digits = $Matches[1].TrimStart('0')
    if (-not $digits) { $digits = '0' }
    $multiplier = switch ($Matches[2]) {
        'm' { 60 }; 'h' { 3600 }; 'd' { 86400 }; default { 1 }
    }
    $now = [DateTimeOffset](Get-Date -ErrorAction Stop)
    $epoch = $now.ToUnixTimeSeconds()
    if ($epoch -lt 0) { throw 'Invalid Podman clock before Unix epoch' }
    $bound = ([Math]::Floor($epoch / [decimal]$multiplier)).ToString([Globalization.CultureInfo]::InvariantCulture)
    if ($digits.Length -gt $bound.Length -or
        ($digits.Length -eq $bound.Length -and [String]::CompareOrdinal($digits, $bound) -gt 0)) {
        throw 'Excessive Podman retention; retained inventories'
    }
    $seconds = [long]$digits * $multiplier
    return $now.AddSeconds(-$seconds)
}

function Test-PodmanImageEligible {
    param([string]$ImageId, [DateTimeOffset]$Cutoff)
    try {
        $items = @(Get-PodmanJson -PodmanArgs @('image', 'inspect', $ImageId) -Inspection)
        if ($items.Count -ne 1) { return $false }
        $image = $items[0]
        if ((ConvertTo-PodmanImageId $image.Id) -cne $ImageId -or $image.Created -isnot [string] -or
            $null -eq $image.RepoTags -or $image.RepoTags -isnot [Array]) { return $false }
        if ($image.Created -notmatch '^\d{4}-\d{2}-\d{2}T') { return $false }
        $created = [DateTimeOffset]::Parse($image.Created, [Globalization.CultureInfo]::InvariantCulture)
        if ($created -ge $Cutoff) { return $false }
        $prefix = $KeepTagPrefix -creplace '^localhost/', ''
        if (-not $prefix) { return $false }
        foreach ($tag in $image.RepoTags) {
            if ($tag -isnot [string] -or $tag -cnotmatch '^[a-z0-9][a-z0-9._:/@-]*$') { return $false }
            $normalized = $tag -creplace '^localhost/', ''
            if ($normalized.StartsWith($prefix, [StringComparison]::Ordinal)) {
                Write-GcLog ("podman: keep {0} ({1})" -f $ImageId, $tag)
                return $false
            }
        }
        return $true
    }
    catch { return $false }
}

function Get-PodmanContainers {
    param([DateTimeOffset]$Cutoff, [switch]$Collect)
    $result = Invoke-PodmanGuarded -PodmanArgs @('ps', '--all', '--quiet', '--no-trunc') -TimeoutSec $PodmanTimeoutSec
    if ($null -eq $result -or $result.ExitCode -ne 0) { throw 'Container enumeration failed' }
    $references = @()
    foreach ($containerId in @($result.Output -split '\s+' | Where-Object { $_ })) {
        if ($containerId -cnotmatch '^[a-f0-9]+$') { throw 'Invalid container ID' }
        $items = @(Get-PodmanJson -PodmanArgs @('container', 'inspect', $containerId) -Inspection)
        if ($items.Count -ne 1) { throw 'Invalid container inspection' }
        $container = $items[0]
        if ($container.Id -cne $containerId -or $container.Image -isnot [string] -or
            $container.Created -isnot [string] -or
            $container.State.Status -cnotmatch '^(created|initialized|running|stopped|paused|exited|removing|stopping)$') {
            throw 'Invalid container metadata'
        }
        $references += ConvertTo-PodmanImageId $container.Image
        if (-not $Collect -or $container.State.Status -cnotmatch '^(exited|stopped|created)$') { continue }
        try {
            if ($container.Created -notmatch '^\d{4}-\d{2}-\d{2}T') { continue }
            $created = [DateTimeOffset]::Parse($container.Created, [Globalization.CultureInfo]::InvariantCulture)
        }
        catch { continue }
        if ($created -ge $Cutoff) { continue }
        if ($DryRun) { Write-GcLog ("DRY-RUN: would remove podman container {0}" -f $containerId) }
        elseif ($Force -or -not (Test-ForeignWorker)) {
            $removed = Invoke-PodmanGuarded -PodmanArgs @('rm', $containerId) -TimeoutSec $PodmanTimeoutSec
            if ($null -eq $removed -or $removed.ExitCode -ne 0) {
                Write-GcLog ("podman: retained container {0} (removal refused)" -f $containerId)
            }
        }
    }
    return $references
}

function Invoke-PodmanGc {
    if ($SkipPodman) { Write-GcLog 'podman: -SkipPodman requested; skipping'; return }
    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        Write-GcLog 'podman: not installed; retained inventories'; return
    }
    try {
        $cli = Invoke-PodmanGuarded -PodmanArgs @('--version') -TimeoutSec ([Math]::Min(60, $PodmanTimeoutSec))
        if ($null -eq $cli -or $cli.ExitCode -ne 0 -or
            $cli.Output -notmatch '^podman version ([0-9]+)\.' -or [int]$Matches[1] -lt 5) { throw 'CLI >=5 required' }
        $info = Get-PodmanJson -PodmanArgs @('info', '--format', 'json')
        if ($info.host.serviceIsRemote -isnot [bool] -or
            $info.version.APIVersion -isnot [string] -or $info.version.APIVersion -notmatch '^[0-9]+\.' -or
            $info.version.Version -isnot [string] -or
            $info.version.Version -notmatch '^([0-9]+)\.' -or [int]$Matches[1] -lt 5) { throw 'Podman engine metadata and version >=5 required' }
        $cutoff = Get-PodmanCutoff
        $null = Get-PodmanContainers -Cutoff $cutoff -Collect
        $images = Invoke-PodmanGuarded -PodmanArgs @('images', '--quiet', '--no-trunc') -TimeoutSec $PodmanTimeoutSec
        if ($null -eq $images -or $images.ExitCode -ne 0) { throw 'Image enumeration failed' }
        foreach ($wireId in @($images.Output -split '\s+' | Where-Object { $_ } | Sort-Object -Unique)) {
            try { $imageId = ConvertTo-PodmanImageId $wireId }
            catch { continue }
            if (-not (Test-PodmanImageEligible -ImageId $imageId -Cutoff $cutoff)) { continue }
            $references = @(Get-PodmanContainers -Cutoff $cutoff)
            if ($references -ccontains $imageId) { continue }
            if (-not $Force -and (Test-ForeignWorker)) { continue }
            # Final metadata observation. Arbitrary later retags are not fenced.
            if (-not (Test-PodmanImageEligible -ImageId $imageId -Cutoff $cutoff)) { continue }
            if ($DryRun) { Write-GcLog ("DRY-RUN: would remove podman image {0}" -f $imageId); continue }
            $removed = Invoke-PodmanGuarded -PodmanArgs @('rmi', '--no-prune', $imageId) -TimeoutSec $PodmanTimeoutSec
            if ($null -eq $removed -or $removed.ExitCode -ne 0) {
                Write-GcLog ("podman: retained image {0} (removal refused)" -f $imageId)
            }
        }
    }
    catch { Write-GcLog ("podman: {0}; retained remaining inventories" -f $_) }
}

# Stamped into a workspace whenever a job finishes there. See .NOTES.
$Marker = '.runner-gc-last-used'

# The runner owns these; only the sibling directories are repo workspaces.
# Matching on a leading underscore instead would permanently exclude a repo
# actually named `_foo`.
$RunnerManaged = @('_actions', '_diag', '_PipelineMapping', '_temp', '_tool', '_update')

function ConvertTo-Hours {
    <# Read podman's own age syntax (2h, 90m, 7d) as a number of hours. #>
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

function Test-ForeignWorker {
    $ancestors = Get-AncestorProcessId
    $foreign = @(
        Get-Process -Name 'Runner.Worker' -ErrorAction SilentlyContinue |
            Where-Object { $ancestors -notcontains $_.Id }
    )
    return ($foreign.Count -gt 0)
}

if (-not $Force -and (Test-ForeignWorker)) {
    Write-GcLog 'SKIP: another runner job is executing (Runner.Worker alive)'
    exit 0
}

if ($PodmanOnly) { Invoke-PodmanGc; exit 0 }

$free = (Get-PSDrive C).Free / 1GB
Write-GcLog ("start (retention={0}) - C: {1:N1} GB free" -f $Retention, $free)

# --- Podman (no automatic build/mount-cache reclamation, ADR 0067) ------------
Invoke-PodmanGc

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

    # ~/.bun/bin rename-away litter: the hub's setup-bun-canary renames a
    # BUSY bun.exe/bunx.exe aside as *.stale-<guid> instead of fighting the
    # image lock (example-org/.github#70; bunx is a HARDLINK of bun, so any live
    # bun process blocks an overwrite - example-repo-a light-0201). Its own sweep
    # runs only at the next install and is best-effort, so on a box where an
    # interactive bun lives for hours the 86MB-per-file litter can sit
    # indefinitely. 24h floor, deliberately NOT the 2h retention: a fresher
    # stale file may still be held by the very process it was renamed away
    # from (deleting under a live image fails; the floor keeps the GC from
    # churning while a long interactive session holds it).
    $bunBin = Join-Path $env:USERPROFILE '.bun\bin'
    if (Test-Path $bunBin) {
        $staleCutoff = (Get-Date).AddHours(-24)
        $bunStale = @(Get-ChildItem $bunBin -Filter '*.stale-*' -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt $staleCutoff })
        if ($DryRun) {
            if ($bunStale.Count) {
                Write-GcLog ("DRY-RUN: would sweep {0} .bun\bin *.stale-* file(s)" -f $bunStale.Count)
            }
        }
        elseif ($bunStale.Count) {
            $bunStale | Remove-Item -Force -ErrorAction SilentlyContinue
            Write-GcLog ("bun: swept {0} rename-away stale file(s) older than 24h" -f $bunStale.Count)
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
