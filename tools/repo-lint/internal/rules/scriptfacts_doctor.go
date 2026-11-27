package rules

import (
	"fmt"
	"regexp"
	"slices"
	"strings"
)

// installSh is the Unix installer; macBrewfile is the Mac's package manifest.
const (
	installSh   = "install.sh"
	macBrewfile = "dump/macbook/Brewfile"
)

// doctorFacts: doctor keeps the checks the tests that read scripts/doctor.sh
// held: the Windows branch, the WinGet shadow, the rogue npm globals, the
// PowerShell profile states, zsh, Podman and the retired Python tools.
// Findings name the removed test.
func doctorFacts() Rule {
	return factRule(
		"doctor-facts",
		"doctor checks what breaks a host silently and names the fix, and only reads: the Windows branch, shadowed CLIs, the profile blocks, zsh, Podman",
		[]string{doctorScript},
		doctorFactList,
	)
}

// installFacts: install.sh keeps the steps the tests that read it held.
func installFacts() Rule {
	return factRule(
		"install-facts",
		"install.sh runs every step its tests name",
		[]string{installSh},
		[]scriptFact{
			// tests/unit/test_install_zsh_steps.py
			fact("test_install_sh_runs_the_zsh_step", matches(installSh, `(?m)^step_zsh$`)),
		},
	)
}

var doctorFactList = []scriptFact{
	// tests/unit/test_doctor_windows.py (its fixture: the Windows branch)
	fact("test_doctor_checks_persisted_path_reaches_cygpath",
		onWindowsBranch(has(doctorScript, "cygpath -w /usr/bin", "GetEnvironmentVariable", "SetEnvironmentVariable"))),
	fact("test_doctor_checks_deploy_managed_state",
		onWindowsBranch(has(doctorScript, "config/mise/config.toml", "starship init", "mise activate", "mise node corepack", "just deploy"))),
	fact("test_doctor_checks_windows_uv_hardening",
		onWindowsBranch(matches(doctorScript, `APPDATA.*uv[/\\]uv\.toml|uv[/\\]?uv\.toml`),
			has(doctorScript, "APPDATA", "just harden-env"))),
	fact("test_doctor_checks_scoop_unix_clis",
		onWindowsBranch(has(doctorScript, "jq", "shellcheck", "scoop install jq shellcheck"))),
	fact("test_doctor_checks_persisted_path_reaches_git_cmd",
		onWindowsBranch(has(doctorScript, "win-git-cmd", "cygpath -w /cmd", "harden-env"))),
	fact("test_doctor_checks_machine_path_sanity",
		onWindowsBranch(has(doctorScript, "win-machine-path", "ExpandString", "ELEVATED"))),
	fact("test_doctor_powershell_fallback_when_system32_off_path",
		onWindowsBranch(has(doctorScript, "WindowsPowerShell/v1.0/powershell.exe"))),
	// tests/unit/test_doctor_winget_shadow.py
	fact("test_doctor_checks_the_winget_links_dir",
		anyOf(has(doctorScript, "WinGet/Links"), has(doctorScript, `WinGet\Links`))),
	fact("test_doctor_covers_every_mise_managed_ai_cli", wingetSectionNamesEveryCli),
	fact("test_doctor_reports_winget_shadow_with_a_fix", has(doctorScript, "winget-shadow", "winget uninstall")),
	// tests/unit/test_doctor_npm_rogue.py
	fact("test_doctor_runs_rogue_detector",
		has(doctorScript, "rogue_npm_globals.sh detect", "npm-rogue", "just prune-rogue-npm-globals")),
	fact("test_doctor_rogue_check_is_cross_platform",
		order(doctorScript, "rogue_npm_globals.sh detect", `case "$(uname -s)" in`)),
	fact("test_doctor_warns_not_ok_on_scan_error", rogueScanErrorWarns),
	// tests/unit/test_ps_profile_block_order.py and test_ps_profile_mise_block.py
	fact("test_doctor_reports_a_misordered_profile", has(doctorScript, "ps_profile_starship_before_mise")),
	fact("test_doctor_reports_both_states_and_writes_nothing",
		has(doctorScript, "ps_profile_mise_stale", "ps_profile_mise_unclosed"),
		lacks(doctorScript, "ps_profile_mise_upgrade")),
	// tests/unit/test_install_zsh_steps.py
	fact("test_doctor_reports_zsh_on_linux", zshBlockNamesTheFix),
	// tests/unit/test_cli_release_age_policy.py
	fact("test_doctor_checks_required_podman_cli_and_selected_engine",
		has(doctorScript, "podman --version", "podman info --format", "has podman-compose", "log_err 'podman'", "log_err 'podman-compose'"),
		lacks(doctorScript, "docker info", "podman machine init", "podman machine start")),
	// tests/unit/test_retired_python_tools.py
	fact("test_doctor_runs_the_detector_cross_platform",
		has(doctorScript, "retired_python_tools.sh detect", "python-retired", "just prune-retired-python-tools"),
		order(doctorScript, "retired_python_tools.sh detect", `case "$(uname -s)" in`)),
}

// doctorWindowsBranch is the test fixture's regex: the MINGW/MSYS/CYGWIN
// arm of doctor's uname case, up to its first ";;".
var doctorWindowsBranch = regexp.MustCompile(`case\s+"\$\(uname\s+-s\)"\s+in\s*\n\s*MINGW\*\|MSYS\*\|CYGWIN\*\)([\s\S]*?);;`)

// onWindowsBranch runs checks over doctor's Windows branch only.
func onWindowsBranch(checks ...factCheck) factCheck {
	return func(files map[string]string) []string {
		m := doctorWindowsBranch.FindStringSubmatch(files[doctorScript])
		if m == nil {
			return []string{doctorScript + " has no uname-gated MINGW/MSYS/CYGWIN section"}
		}
		branch := map[string]string{doctorScript: m[1]}
		var out []string
		for _, c := range checks {
			for _, problem := range c(branch) {
				out = append(out, problem+" (in the Windows branch)")
			}
		}
		return out
	}
}

// pySlice is text[start:] with Python's reading of a negative start.
func pySlice(text string, start int) string {
	if start < 0 {
		start = max(len(text)+start, 0)
	}
	return text[min(start, len(text)):]
}

// wingetSectionNamesEveryCli: from the first "WinGet" on (the test's
// text[text.find("WinGet"):], the last character when it is missing), each
// mise-managed AI CLI is named as a word.
func wingetSectionNamesEveryCli(files map[string]string) []string {
	text := files[doctorScript]
	section := pySlice(text, strings.Index(text, "WinGet"))
	var out []string
	for _, cli := range []string{"codex", "claude", "copilot", "pi"} {
		if !regexp.MustCompile(`\b` + cli + `\b`).MatchString(section) {
			out = append(out, cli+" is mise-managed but not checked for a WinGet copy")
		}
	}
	return out
}

var (
	rogueWarnAfterRc = regexp.MustCompile(`(?s)rc"?\s*-ne\s+0.*\n.*log_warn`)
	rogueRcBranch    = regexp.MustCompile(`\[ "\$rc" -ne 0 \]`)
)

// rogueScanErrorWarns: a failed detector run warns, never reads as clean.
// The window is the test's text[text.index("npm-rogue") - 400:].
func rogueScanErrorWarns(files map[string]string) []string {
	text := files[doctorScript]
	at := strings.Index(text, "npm-rogue")
	if at < 0 {
		return []string{doctorScript + ` must hold "npm-rogue"`}
	}
	if !rogueWarnAfterRc.MatchString(pySlice(text, at-400)) && !rogueRcBranch.MatchString(text) {
		return []string{"doctor must branch on the detector's non-zero exit and warn"}
	}
	return nil
}

// zshBlockNamesTheFix: from the zsh marker on, doctor warns and names both
// fixes.
func zshBlockNamesTheFix(files map[string]string) []string {
	_, block, ok := strings.Cut(files[doctorScript], "# zsh is the supported interactive shell")
	if !ok {
		return []string{doctorScript + " lost its zsh block"}
	}
	return has(doctorScript, "log_warn 'zsh'", "sudo apt-get install -y zsh", "chsh -s")(map[string]string{doctorScript: "# zsh is the supported interactive shell" + block})
}

// brewDocker is the Docker providers the Mac must not hold.
var brewDocker = []string{"docker", "docker-buildx", "docker-compose", "docker-credential-helper", "docker-desktop", "orbstack"}

var (
	brewDockerLine = regexp.MustCompile(`(?m)^_brew_docker='([^']+)'$`)
	brewfileEntry  = regexp.MustCompile(`(?m)^(?:brew|cask) "([^"]+)"`)
)

// brewfileDockerFree: the Mac provisions Podman and no Docker provider, and
// doctor names exactly the providers it must flag.
func brewfileDockerFree() Rule {
	return factRule(
		"brewfile-docker-free",
		"the Mac provisions Podman, never a Docker provider, and doctor flags exactly the providers the manifest must not hold",
		[]string{doctorScript, macBrewfile},
		[]scriptFact{
			// tests/unit/test_doctor_os_gating.py
			fact("test_doctor_and_the_brewfile_test_forbid_the_same_packages", doctorNamesTheDockerProviders),
			// tests/unit/test_cli_release_age_policy.py
			fact("test_mac_package_manifest_provisions_podman_without_docker_providers", brewfileHasNoDockerProvider),
		},
	)
}

func doctorNamesTheDockerProviders(files map[string]string) []string {
	m := brewDockerLine.FindStringSubmatch(files[doctorScript])
	if m == nil {
		return []string{"doctor.sh lost its Docker package list (_brew_docker='...')"}
	}
	got := strings.Fields(m[1])
	slices.Sort(got)
	got = slices.Compact(got)
	want := slices.Sorted(slices.Values(brewDocker))
	if !slices.Equal(got, want) {
		return []string{fmt.Sprintf("doctor's _brew_docker must be %v, not %v", want, got)}
	}
	return nil
}

func brewfileHasNoDockerProvider(files map[string]string) []string {
	var packages []string
	for _, m := range brewfileEntry.FindAllStringSubmatch(files[macBrewfile], -1) {
		packages = append(packages, m[1])
	}
	var out []string
	if !slices.Contains(packages, "podman") {
		out = append(out, macBrewfile+" must provision podman")
	}
	for _, p := range brewDocker {
		if slices.Contains(packages, p) {
			out = append(out, macBrewfile+" must not hold the Docker provider "+p)
		}
	}
	return out
}
