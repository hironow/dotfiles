package rules

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strings"
	"unicode"
	"unicode/utf8"
)

// bootstrapPs1 is the Windows one-liner that connects a bare machine to the
// just chain (ADR 0039).
const bootstrapPs1 = "bootstrap.ps1"

// bootstrapFacts: bootstrap.ps1 keeps what tests/unit/test_bootstrap_ps1.py's
// text checks held. They read the file as ASCII; test_ascii_only, which
// stays, fails on any other byte. "Code" is the lines that are not comments.
func bootstrapFacts() Rule {
	return factRule(
		"bootstrap-facts",
		"the Windows bootstrap clones over HTTPS, deploys only hironow/dotfiles, runs the just chain in order through a login Git Bash, and isolates scoop and winget",
		[]string{bootstrapPs1},
		bootstrapFactList,
	)
}

// bootstrapChain is the just chain, in the order bootstrap runs it.
var bootstrapChain = []string{"add-scoop", "deploy", "harden-env", "sync-agents", "restore-skills-lock", "doctor"}

var bootstrapFactList = []scriptFact{
	fact("test_runs_full_chain_in_order", chainInOrder),
	fact("test_clones_over_https_never_ssh",
		has(bootstrapPs1, "https://github.com/hironow/dotfiles"),
		onBootstrapCode(lacks(bootstrapPs1, "git@github.com"))),
	fact("test_no_submodule_update", onBootstrapCode(lacksFold(bootstrapPs1, "submodule"))),
	fact("test_invokes_git_bash_as_login_shell", matches(bootstrapPs1, `bash\.exe`), has(bootstrapPs1, "-lc")),
	fact("test_resolves_git_bash_via_scoop_prefix", has(bootstrapPs1, "scoop prefix git")),
	fact("test_gates_on_minimum_just_version", has(bootstrapPs1, "scoop update just"), matches(bootstrapPs1, `1\.51`)),
	fact("test_base_tool_set_membership", baseToolSet, onBootstrapCode(has(bootstrapPs1, "scoop install"))),
	fact("test_installs_only_missing_tools", onBootstrapCode(matches(bootstrapPs1, `Get-Command\s+\$_`))),
	fact("test_handles_execution_policy", has(bootstrapPs1, "ExecutionPolicy")),
	fact("test_refreshes_path_after_scoop",
		matches(bootstrapPs1, `GetEnvironmentVariable\(\s*['"]Path['"]`, `\$env:Path\s*=\s*"\$env:Path;`),
		has(bootstrapPs1, "ExpandEnvironmentVariables")),
	fact("test_scoop_mutations_run_out_of_process", scoopMutationsOutOfProcess),
	fact("test_scoop_prefix_trusts_exit_code", onBootstrapCode(matches(bootstrapPs1, `scoop prefix git[\s\S]{0,200}LASTEXITCODE`))),
	fact("test_guards_existing_clone_identity", matches(bootstrapPs1, `remote\s+get-url\s+origin`)),
	fact("test_reads_dotfiles_host_env", has(bootstrapPs1, "DOTFILES_HOST")),
	fact("test_winget_exit_codes_are_answers_not_errors", wingetThroughInvokeWinget),
	fact("test_never_invokes_forbidden_package_managers",
		noMatch(bootstrapPs1, `\bnpm\b`, `\byarn\b`, `\bpnpm\b`, `\bcorepack\b`)),
}

// onBootstrapCode runs checks over the test's _code(): the lines of
// text.splitlines() that do not start with "#" after lstrip(), joined by "\n".
func onBootstrapCode(checks ...factCheck) factCheck {
	return func(files map[string]string) []string {
		code := maps.Clone(files)
		code[bootstrapPs1] = strings.Join(pyCodeLines(files[bootstrapPs1]), "\n")
		var out []string
		for _, c := range checks {
			for _, problem := range c(code) {
				out = append(out, problem+" (outside a comment)")
			}
		}
		return out
	}
}

// pyCodeLines is the lines of Python's str.splitlines() that do not start
// with "#" after str.lstrip().
func pyCodeLines(text string) []string {
	var out []string
	for _, line := range pySplitlines(text) {
		if !strings.HasPrefix(strings.TrimLeftFunc(line, pyIsSpace), "#") {
			out = append(out, line)
		}
	}
	return out
}

// pySplitlines is str.splitlines(): it breaks at \n, \r, \r\n, \v, \f,
// \x1c-\x1e, \x85, U+2028 and U+2029, and keeps no empty last line.
func pySplitlines(text string) []string {
	var lines []string
	start := 0
	for i := 0; i < len(text); {
		r, size := utf8.DecodeRuneInString(text[i:])
		switch r {
		case '\n', '\r', '\v', '\f', 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029:
			lines = append(lines, text[start:i])
			i += size
			if r == '\r' && i < len(text) && text[i] == '\n' {
				i++
			}
			start = i
		default:
			i += size
		}
	}
	if start < len(text) {
		lines = append(lines, text[start:])
	}
	return lines
}

// pyIsSpace is str.isspace() for one character.
func pyIsSpace(r rune) bool {
	return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f
}

// chainInOrder: each recipe runs through Invoke-Just, in dependency order.
func chainInOrder(files map[string]string) []string {
	text := files[bootstrapPs1]
	var out []string
	var positions []int
	for _, recipe := range bootstrapChain {
		loc := regexp.MustCompile(`Invoke-Just\s+["']` + regexp.QuoteMeta(recipe) + `\b`).FindStringIndex(text)
		if loc == nil {
			out = append(out, fmt.Sprintf("%s must run 'just %s' via Invoke-Just", bootstrapPs1, recipe))
			continue
		}
		positions = append(positions, loc[0])
	}
	if len(out) == 0 && !slices.IsSorted(positions) {
		out = append(out, "the chain must run in order: "+strings.Join(bootstrapChain, " -> "))
	}
	return out
}

var (
	baseToolsDecl = regexp.MustCompile(`\$baseTools\s*=\s*@\(([^)]*)\)`)
	quotedWord    = regexp.MustCompile(`'([^']+)'`)
)

// baseToolSet: the base set covers the chain floor, mise and pwsh.
func baseToolSet(files map[string]string) []string {
	m := baseToolsDecl.FindStringSubmatch(strings.Join(pyCodeLines(files[bootstrapPs1]), "\n"))
	if m == nil {
		return []string{bootstrapPs1 + " must declare its base tool set as $baseTools = @(...)"}
	}
	tools := map[string]bool{}
	for _, q := range quotedWord.FindAllStringSubmatch(m[1], -1) {
		tools[q[1]] = true
	}
	var out []string
	for _, want := range []string{"git", "just", "jq", "mise", "pwsh"} {
		if !tools[want] {
			out = append(out, "the base tool set must hold "+want)
		}
	}
	return out
}

// scoopMutationsOutOfProcess: every code line that installs or updates with
// scoop runs it through cmd /c.
func scoopMutationsOutOfProcess(files map[string]string) []string {
	var out []string
	for _, line := range pyCodeLines(files[bootstrapPs1]) {
		for _, cmd := range []string{"scoop install", "scoop update"} {
			if strings.Contains(line, cmd) && !strings.Contains(line, "cmd /c") {
				out = append(out, fmt.Sprintf("'%s' must run via cmd /c: %s", cmd, strings.TrimSpace(line)))
			}
		}
	}
	return out
}

var (
	invokeWingetBody = regexp.MustCompile(`(?ms)^function Invoke-Winget\b.*?^\}`)
	wingetCall       = regexp.MustCompile(`(?m)^\s*winget\b`)
)

// wingetThroughInvokeWinget: winget's exit codes are answers, so its one call
// sits in Invoke-Winget, which turns off the native-command error preference.
func wingetThroughInvokeWinget(files map[string]string) []string {
	text := files[bootstrapPs1]
	body := invokeWingetBody.FindString(text)
	if body == "" {
		return []string{bootstrapPs1 + " must run winget through function Invoke-Winget"}
	}
	var out []string
	for _, s := range []string{"$PSNativeCommandUseErrorActionPreference = $false", "| Out-Host"} {
		if !strings.Contains(body, s) {
			out = append(out, fmt.Sprintf("Invoke-Winget must hold %q", s))
		}
	}
	if n := len(wingetCall.FindAllStringIndex(text, -1)); n != 1 {
		out = append(out, fmt.Sprintf("every winget call must go through Invoke-Winget: %d winget lines", n))
	}
	return out
}
