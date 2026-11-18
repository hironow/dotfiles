# ==============================================================================
# Install-RunHidden: copy run-hidden.exe for dotfiles' scheduled tasks
# ------------------------------------------------------------------------------
# dotfiles' Windows scheduled tasks start through run-hidden (tools/run-hidden)
# so that a task running in the owner's logon session opens no console window
# (docs/runbook/windows-host.md). A task keeps its launcher running for as long
# as its program runs - the WSL keepalive never ends - and Windows cannot
# overwrite a running exe. So the copy lives in a directory named by its
# content hash: the same content returns the same path and is never written
# again, new content gets a new directory, and the installers point the tasks
# at it. Old directories stay; a task may still run them.
#
# Dot-source it, then:  $runHidden = Install-RunHidden -Source <built exe>
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a BOM-less
# UTF-8 script as ANSI.
# ==============================================================================

function Install-RunHidden {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [string]$Root = (Join-Path $env:LOCALAPPDATA 'dotfiles\run-hidden')
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "run-hidden is not built: $Source (run: just run-hidden-build)"
    }
    $hash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
    $dir = Join-Path $Root $hash.Substring(0, 16)
    $dest = Join-Path $dir 'run-hidden.exe'
    if (Test-Path -LiteralPath $dest) {
        $have = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($have -ne $hash) {
            throw "run-hidden copy $dest does not match its directory name - not replacing a file this installer did not write"
        }
        return $dest
    }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    # Copy under a temporary name, check it, then give it its real name: a
    # half-written copy must never be the path a task starts.
    $partial = $dest + '.partial'
    Copy-Item -LiteralPath $Source -Destination $partial -Force
    $copied = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($copied -ne $hash) {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        throw "run-hidden copy to $partial does not match its source"
    }
    Move-Item -LiteralPath $partial -Destination $dest
    return $dest
}
