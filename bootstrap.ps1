# bootstrap.ps1 - Windows native bootstrap for hironow/dotfiles (ADR 0039).
#
# One-liner (Windows PowerShell 5.1 or pwsh):
#   irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex
# Pick the scoop manifest host (default: windows):
#   $env:DOTFILES_HOST = 'windows'; irm ... | iex
#
# Scope: zero -> scoop/git/just/jq/mise/pwsh -> HTTPS clone -> the existing
# just chain (add-scoop, deploy, harden-env, sync-agents, restore-skills-lock,
# doctor). Submodules and the SSH remote are operator steps AFTER bootstrap
# (all but one submodule use git@github.com URLs; a bare machine has no keys).
#
# This file must stay ASCII-only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI
# and irm|iex decodes without a charset.

[CmdletBinding()]
param(
    # Which dump/<host>/scoop.json to restore. irm|iex cannot bind parameters,
    # so $env:DOTFILES_HOST (dump_host.sh's primary interface) is the
    # one-liner's knob; the parameter serves -File invocations.
    [string]$SourceHost = $(if ($env:DOTFILES_HOST) { $env:DOTFILES_HOST } else { 'windows' })
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$RepoUrl = 'https://github.com/hironow/dotfiles.git'
$RepoDir = Join-Path $HOME 'dotfiles'
$MinJust = [version]'1.51'

function Write-Step([string]$msg) { Write-Host "==> $msg" }
function Write-Warn2([string]$msg) { Write-Host "WARN $msg" -ForegroundColor Yellow }

# Scoop writes new shims to the User PATH in the registry; the current
# process never sees them on its own.
function Update-PathFromRegistry {
    # APPEND the registry PATH, never replace: the inherited process PATH can
    # legitimately hold entries the registry lacks (seen live: git resolved
    # only via the parent shell, and the registry-only rebuild "lost" git
    # mid-run). Machine PATH is REG_EXPAND_SZ and GetEnvironmentVariable
    # returns %SystemRoot%-style entries unexpanded - expand them or System32
    # (powershell.exe) silently drops off.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $registry = [Environment]::ExpandEnvironmentVariables("$machine;$user")
    $env:Path = "$env:Path;$registry"
}

# --- 0. Execution policy (scoop's installer aborts under Restricted) --------
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -notin @('Unrestricted', 'RemoteSigned', 'Bypass')) {
    Write-Step "Setting CurrentUser execution policy to RemoteSigned (was: $policy)"
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
}

# --- 1. scoop --------------------------------------------------------------
if (-not (Get-Command scoop -ErrorAction SilentlyContinue)) {
    Write-Step 'Installing scoop (non-admin)'
    Invoke-RestMethod -Uri 'https://get.scoop.sh' | Invoke-Expression
    Update-PathFromRegistry
}

# --- 2. base toolset -------------------------------------------------------
# git/just/jq: the just-chain floor. mise: deploy's global toolset install and
# every UV_RUN recipe go through `mise exec`. pwsh: `just deploy` writes the
# PowerShell 7 profile path, which is dead config without pwsh.
# Only install what the machine lacks: an unconditional install would add a
# second copy next to an existing Program Files git/pwsh and let scoop shims
# shadow it.
$baseTools = @('git', 'just', 'jq', 'mise', 'pwsh')
$missingTools = @($baseTools | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
# In PowerShell a bare `scoop` runs shims\scoop.ps1 IN-PROCESS, so a crash
# inside scoop's own scripts (seen live: scoop-update.ps1 null-method error
# mid-update, leaving the app shim-less and "Install failed") terminates
# bootstrap under ErrorActionPreference=Stop. cmd /c isolates every scoop
# mutation in its own process; only the exit code comes back.
if ($missingTools.Count -gt 0) {
    Write-Step "Installing missing base tools via scoop: $($missingTools -join ', ')"
    cmd /c "scoop install $($missingTools -join ' ')"
    Update-PathFromRegistry
} else {
    Write-Step 'Base toolset already present (git, just, jq, mise, pwsh)'
}

# A stale scoop just resolves bash to WSL (<=1.45) and rejects this repo's
# justfile attributes; refresh the scoop copy when scoop owns one (even if a
# newer mise just currently shadows it), then gate hard on whatever wins PATH.
$null = cmd /c 'scoop prefix just' 2>$null
if ($LASTEXITCODE -eq 0) {
    cmd /c 'scoop update just'
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 'just update via scoop reported errors - relying on the version gate below.'
    }
    Update-PathFromRegistry
}
$justVersion = [version]((just --version) -replace '[^0-9.]', '')
if ($justVersion -lt $MinJust) {
    throw "just $justVersion < $MinJust - update failed; remove and reinstall just via scoop, then re-run."
}

# --- 3. repo ---------------------------------------------------------------
if (-not (Test-Path (Join-Path $RepoDir '.git'))) {
    Write-Step "Cloning $RepoUrl -> $RepoDir (HTTPS; switch to SSH later if you like)"
    git clone $RepoUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { throw 'git clone failed.' }
} else {
    # The justfile hardcodes ~/dotfiles paths; never deploy from a stranger's tree.
    $origin = git -C $RepoDir remote get-url origin
    if ($origin -notmatch 'hironow/dotfiles') {
        throw "$RepoDir exists but origin is '$origin' (expected hironow/dotfiles) - refusing to deploy from it."
    }
    Write-Step "Using existing clone at $RepoDir (not pulling; your tree is yours)"
}

# --- 4. Git Bash -----------------------------------------------------------
# A bare 'bash' resolves to System32's WSL bash ahead of Git Bash, and the
# scoop shim's parent has no bin\bash.exe - resolve explicitly.
$bashCandidates = @()
$gitPrefix = cmd /c 'scoop prefix git' 2>$null
# scoop prints "Could not find app path" to stdout with a nonzero exit when
# git is not scoop-installed - trust the exit code, not the output.
if ($LASTEXITCODE -eq 0 -and $gitPrefix) {
    $bashCandidates += (Join-Path $gitPrefix 'bin\bash.exe')
}
$bashCandidates += (Join-Path $env:ProgramFiles 'Git\bin\bash.exe')
$gitBash = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gitBash) {
    throw "Git Bash not found (tried: $($bashCandidates -join ', ')) - cannot run shebang recipes."
}

# Login shell (-lc) is mandatory: non-login Git Bash lacks /usr/bin (cygpath)
# on PATH and every shebang recipe (deploy, add-scoop) fails.
function Invoke-Just {
    param([string]$Recipe, [switch]$WarnOnly)
    Write-Step "just $Recipe"
    & $gitBash -lc "cd ~/dotfiles && just $Recipe"
    if ($LASTEXITCODE -ne 0) {
        if ($WarnOnly) {
            Write-Warn2 "just $Recipe failed (exit $LASTEXITCODE); continuing - it is best-effort."
            return $false
        }
        throw "just $Recipe failed (exit $LASTEXITCODE)."
    }
    return $true
}

# --- 5. the chain ----------------------------------------------------------
# warn-continue: add-scoop (manifest may not cover this host yet) and
# restore-skills-lock (best-effort upstream HEAD by design).
# hard-fail: deploy, harden-env, sync-agents.
# doctor: reported, but does not decide bootstrap's exit.
$null = Invoke-Just "add-scoop $SourceHost" -WarnOnly
Update-PathFromRegistry
$null = Invoke-Just 'deploy'
$null = Invoke-Just 'harden-env'
$null = Invoke-Just 'sync-agents'
$null = Invoke-Just 'restore-skills-lock' -WarnOnly
$doctorOk = Invoke-Just 'doctor' -WarnOnly

Write-Host ''
Write-Step 'Bootstrap complete.'
if (-not $doctorOk) {
    Write-Warn2 'doctor reported issues - review its output above and re-run "just doctor" after fixing.'
}
Write-Host 'Next steps:'
Write-Host '  1. Open a NEW pwsh (PowerShell 7) session - the deployed $PROFILE (starship + mise activate) applies there.'
Write-Host '  2. Optional operator steps (SSH remote, upstream trees): see README.md Installation.'
