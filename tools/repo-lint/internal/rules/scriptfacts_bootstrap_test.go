package rules

import (
	"slices"
	"testing"
)

// bootstrapFixture keeps git@github.com and "submodule" in a comment: those
// tests read only the code.
const bootstrapFixture = `param([string]$SourceHost = $(if ($env:DOTFILES_HOST) { $env:DOTFILES_HOST } else { 'windows' }))
$RepoUrl = 'https://github.com/hironow/dotfiles.git'
$MinJust = [version]'1.51'
function Update-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $registry = [Environment]::ExpandEnvironmentVariables("$machine")
    $env:Path = "$env:Path;$registry"
}
function Invoke-Winget([string[]]$Arguments) {
    $PSNativeCommandUseErrorActionPreference = $false
    winget @Arguments | Out-Host
    return $LASTEXITCODE
}
$policy = Get-ExecutionPolicy -Scope CurrentUser
$baseTools = @('git', 'just', 'jq', 'mise', 'pwsh')
$missingTools = @($baseTools | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
cmd /c "scoop install $($missingTools -join ' ')"
cmd /c 'scoop update just'
# Never git@github.com here; the Submodule step is the operator's.
$origin = git -C $RepoDir remote get-url origin
$gitPrefix = cmd /c 'scoop prefix git' 2>$null
if ($LASTEXITCODE -eq 0 -and $gitPrefix) { $bashCandidates += (Join-Path $gitPrefix 'bin\bash.exe') }
& $gitBash -lc "cd ~/dotfiles && just $Recipe"
$null = Invoke-Just "add-scoop $SourceHost" -WarnOnly
$null = Invoke-Just 'deploy'
$null = Invoke-Just 'harden-env'
$null = Invoke-Just 'sync-agents'
$null = Invoke-Just 'restore-skills-lock' -WarnOnly
$doctorOk = Invoke-Just 'doctor' -WarnOnly
`

func bootstrapBase() Inputs { return Inputs{bootstrapPs1: bootstrapFixture} }

func TestBootstrapFacts(t *testing.T) {
	b := bootstrapPs1
	runCases(t, bootstrapFacts(), bootstrapBase, []ruleCase{
		{"harden-env runs before deploy", edit(b, "$null = Invoke-Just 'deploy'\n$null = Invoke-Just 'harden-env'\n", "$null = Invoke-Just 'harden-env'\n$null = Invoke-Just 'deploy'\n"), "test_runs_full_chain_in_order"},
		{"doctor is skipped", edit(b, "$doctorOk = Invoke-Just 'doctor' -WarnOnly\n", ""), "test_runs_full_chain_in_order"},
		{"the clone uses SSH", edit(b, "$RepoUrl = 'https://github.com/hironow/dotfiles.git'", "$RepoUrl = 'git@github.com:hironow/dotfiles.git'"), "test_clones_over_https_never_ssh"},
		{"submodules are updated", edit(b, "$origin = git", "git -C $RepoDir Submodule update --init\n$origin = git"), "test_no_submodule_update"},
		{"a lone CR ends a comment", edit(b, "$origin = git", "# explanation\rgit submodule update --init\n$origin = git"), "test_no_submodule_update"},
		{"Git Bash runs as a non-login shell", edit(b, "-lc", "-c"), "test_invokes_git_bash_as_login_shell"},
		{"Git Bash is found from the shim", edit(b, "cmd /c 'scoop prefix git'", "Split-Path (Get-Command git).Source"), "test_resolves_git_bash_via_scoop_prefix"},
		{"an old just passes", edit(b, "'1.51'", "'1.40'"), "test_gates_on_minimum_just_version"},
		{"pwsh is not in the base set", edit(b, ", 'pwsh')", ")"), "test_base_tool_set_membership"},
		{"every tool is reinstalled", edit(b, "Get-Command $_", "Get-Command git"), "test_installs_only_missing_tools"},
		{"the execution policy is left to chance", edit(b, "$policy = Get-ExecutionPolicy -Scope CurrentUser\n", ""), "test_handles_execution_policy"},
		{"the registry PATH replaces the process PATH", edit(b, "$env:Path = \"$env:Path;$registry\"", "$env:Path = $registry"), "test_refreshes_path_after_scoop"},
		{"scoop updates in process", edit(b, "cmd /c 'scoop update just'", "scoop update just"), "test_scoop_mutations_run_out_of_process"},
		{"scoop's error text is a prefix", edit(b, "if ($LASTEXITCODE -eq 0 -and $gitPrefix)", "if ($gitPrefix)"), "test_scoop_prefix_trusts_exit_code"},
		{"a stranger's clone is deployed", edit(b, "$origin = git -C $RepoDir remote get-url origin\n", ""), "test_guards_existing_clone_identity"},
		{"DOTFILES_HOST is ignored", edit(b, "$(if ($env:DOTFILES_HOST) { $env:DOTFILES_HOST } else { 'windows' })", "'windows'"), "test_reads_dotfiles_host_env"},
		{"winget runs outside Invoke-Winget", edit(b, "$doctorOk = ", "winget upgrade --all\n$doctorOk = "), "test_winget_exit_codes_are_answers_not_errors"},
		{"a lone CR hides a winget line", edit(b, "$doctorOk = ", "Write-Host 'x'\rwinget upgrade --all\r$doctorOk = "), "test_winget_exit_codes_are_answers_not_errors"},
		{"winget errors throw", edit(b, "    $PSNativeCommandUseErrorActionPreference = $false\n", ""), "test_winget_exit_codes_are_answers_not_errors"},
		{"npm installs a CLI", edit(b, "$doctorOk = ", "npm install -g x\n$doctorOk = "), "test_never_invokes_forbidden_package_managers"},
	})
}

func TestPySplitlines(t *testing.T) {
	for _, c := range []struct {
		in   string
		want []string
	}{
		{"", nil},
		{"a\n", []string{"a"}},
		{"a\n\nb", []string{"a", "", "b"}},
		{"a\r\nb\rc\vd\fe\x1cf\u2028g", []string{"a", "b", "c", "d", "e", "f", "g"}},
	} {
		if got := pySplitlines(c.in); !slices.Equal(got, c.want) {
			t.Errorf("pySplitlines(%q) = %q, want %q", c.in, got, c.want)
		}
	}
	if got := pyCodeLines(" \x1f# comment\ncode"); !slices.Equal(got, []string{"code"}) {
		t.Errorf("lstrip must drop \\x1f before a comment: %q", got)
	}
}
