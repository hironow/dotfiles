# Get-PodmanJson from scripts/runner_gc_win.ps1 on Windows PowerShell 5.1, the
# runtime that runs the GC in production (scripts/runner_gc.sh calls
# powershell.exe). Only the function's definition is loaded, through the
# parser, so nothing else of the script runs; Podman is a stub that returns
# fixed JSON. Any failure throws, so powershell.exe -File exits non-zero.
# CI: .github/workflows/test-podman-gc-compat.yaml (windows-powershell-51).
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$version = $PSVersionTable.PSVersion
if ($version.Major -ne 5 -or $version.Minor -ne 1 -or $PSVersionTable.PSEdition -ne 'Desktop') {
    throw ("Windows PowerShell 5.1 Desktop required, got {0} {1}" -f $version, $PSVersionTable.PSEdition)
}

$path = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\scripts\runner_gc_win.ps1')).Path
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw ("runner_gc_win.ps1 does not parse: {0}" -f ($errors -join '; ')) }
$definitions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-PodmanJson'
}, $true))
if ($definitions.Count -ne 1) { throw ("one Get-PodmanJson expected, found {0}" -f $definitions.Count) }

# What Get-PodmanJson reads from the script around it.
$PodmanTimeoutSec = 1
$script:reply = $null
function Invoke-PodmanGuarded {
    param([string[]]$PodmanArgs, [int]$TimeoutSec)
    return $script:reply
}
. ([ScriptBlock]::Create($definitions[0].Extent.Text))

function Assert-Throws {
    param([string]$Case, [scriptblock]$Action, [string]$Message)
    try { $null = & $Action }
    catch {
        if ($Message -and $_.Exception.Message -cne $Message) {
            throw ("{0}: threw '{1}', expected '{2}'" -f $Case, $_.Exception.Message, $Message)
        }
        return
    }
    throw ("{0}: did not throw" -f $Case)
}

$cmdlet = Microsoft.PowerShell.Core\Get-Command -Name ConvertFrom-Json -CommandType Cmdlet
if ($cmdlet.Parameters.ContainsKey('DateKind')) { throw 'ConvertFrom-Json on 5.1 has DateKind; the call under test changed' }

# Podman writes Created as Go's RFC 3339 time: Z or an offset, nanoseconds.
$wireForms = @('2020-01-01T00:00:00Z', '2020-01-01T09:00:00+09:00', '2020-01-01T00:00:00.123456789Z')
foreach ($created in $wireForms) {
    $json = '[{{"Id":"{0}","Created":"{1}","State":{{"Status":"exited"}}}}]' -f ('a' * 64), $created
    $script:reply = @{ ExitCode = 0; Output = $json }
    $items = @(Get-PodmanJson -PodmanArgs @('container', 'inspect', 'abc') -Inspection)
    if ($items.Count -ne 1) { throw ("{0}: one inspection expected, got {1}" -f $created, $items.Count) }
    $value = $items[0].Created
    if ($value -isnot [string] -or $value -cne $created) {
        throw ("{0}: came back as {1} '{2}'" -f $created, $value.GetType().FullName, $value)
    }
}

$script:reply = @{ ExitCode = 0; Output = '{"Id":"abc","Created":"2020-01-01T00:00:00Z"}' }
Assert-Throws 'object inspection' { Get-PodmanJson -PodmanArgs @('container', 'inspect', 'abc') -Inspection } 'Inspection array required'
$script:reply = @{ ExitCode = 0; Output = '[{"Id":"abc","Created":' }
Assert-Throws 'malformed JSON' { Get-PodmanJson -PodmanArgs @('container', 'inspect', 'abc') -Inspection } $null
$script:reply = @{ ExitCode = 1; Output = '[]' }
Assert-Throws 'failed query' { Get-PodmanJson -PodmanArgs @('container', 'inspect', 'abc') -Inspection } 'Podman query failed'
$script:reply = $null
Assert-Throws 'no reply' { Get-PodmanJson -PodmanArgs @('info', '--format', 'json') } 'Podman query failed'

Write-Output ("Get-PodmanJson on Windows PowerShell {0} {1}: {2} Created forms kept as strings; bad replies throw" -f $version, $PSVersionTable.PSEdition, $wireForms.Count)
