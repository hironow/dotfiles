# restore_machine_path.ps1 - guarded repair for a wiped HKLM Machine PATH.
#
# Incident this exists for (seen live 2026-08-16): the Machine PATH value in
# HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment was
# completely EMPTY (len=0). Every fresh shell was born without System32
# (no powershell.exe / where.exe / reg.exe), masked for a long time because
# interactive shells inherited an enriched PATH from their parent process.
# `just doctor` detects this as `win-machine-path` and points here.
#
# Design rules:
#   - DRY-RUN by default: prints current vs proposed and exits. The write
#     happens only with -Apply.
#   - MERGE, never clobber: existing Machine PATH entries are kept; only
#     missing baseline/detected entries are appended. A partial wipe repair
#     must not destroy surviving machine-specific entries.
#   - REG_EXPAND_SZ via Registry.SetValue: SetEnvironmentVariable and setx
#     write REG_SZ, leaving %SystemRoot% unexpanded at logon (= broken).
#   - Self-elevates via UAC (Start-Process -Verb RunAs) so a human approves
#     the machine-scope write.
#   - Optional entries are PROBED with Test-Path, and per-user shim dirs
#     derive from $env:USERPROFILE - nothing machine-specific is hardcoded,
#     so the script ports across hosts.
#   - ASCII-only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
[CmdletBinding()]
param(
    # Perform the registry write (after elevating if needed). Without it the
    # script only previews.
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$regPath = 'HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'

# Core Windows entries every machine needs (kept unexpanded on purpose).
$baseline = @(
    '%SystemRoot%\system32'
    '%SystemRoot%'
    '%SystemRoot%\System32\Wbem'
    '%SYSTEMROOT%\System32\WindowsPowerShell\v1.0\'
    '%SYSTEMROOT%\System32\OpenSSH\'
)

# Common machine-wide tool dirs: include only the ones that exist here.
$probed = @(
    "$env:ProgramFiles\PowerShell\7"
    "$env:ProgramFiles\LLVM\bin"
    "$env:ProgramFiles\Docker\Docker\resources\bin"
    "$env:ProgramFiles\dotnet"
    "${env:ProgramFiles(x86)}\NVIDIA Corporation\PhysX\Common"
    # Per-user shim dirs that the self-hosted runner service (LocalSystem)
    # resolves through the Machine PATH (see memory/ADR 0035 context).
    "$env:USERPROFILE\scoop\shims"
    "$env:USERPROFILE\.bun\bin"
    "$env:USERPROFILE\AppData\Local\mise\shims"
) | Where-Object { $_ -and (Test-Path $_) }

# Current value, UNEXPANDED (DoNotExpandEnvironmentNames) so we merge and
# rewrite %SystemRoot% entries verbatim instead of freezing expanded paths.
$key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')
$current = $key.GetValue(
    'Path', '',
    [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
$currentEntries = @($current -split ';' | Where-Object { $_ -ne '' })

$missing = @(($baseline + $probed) | Where-Object {
        $entry = $_
        -not ($currentEntries | Where-Object {
                $_.TrimEnd('\') -ieq $entry.TrimEnd('\')
            })
    })

Write-Host "Current Machine PATH ($($currentEntries.Count) entries):"
$currentEntries | ForEach-Object { Write-Host "  = $_" }
Write-Host "Missing entries to append ($($missing.Count)):"
$missing | ForEach-Object { Write-Host "  + $_" }

if ($missing.Count -eq 0) {
    Write-Host 'Machine PATH already complete - nothing to do.'
    exit 0
}

if (-not $Apply) {
    Write-Host ''
    Write-Host 'Dry-run only. To write (UAC prompt will appear):'
    Write-Host "  powershell -ExecutionPolicy Bypass -File $PSCommandPath -Apply"
    exit 0
}

$isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'Elevating (approve the UAC prompt)...'
    $psi = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru `
        -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-Apply'
    exit $psi.ExitCode
}

$newValue = (@($currentEntries) + $missing) -join ';'
[Microsoft.Win32.Registry]::SetValue(
    $regPath, 'Path', $newValue,
    [Microsoft.Win32.RegistryValueKind]::ExpandString)
Write-Host "Machine PATH written ($(@($currentEntries).Count + $missing.Count) entries, REG_EXPAND_SZ)."
Write-Host 'Open a NEW shell to pick it up; verify with: just doctor (win-machine-path).'
