package rules

import (
	"fmt"
	"regexp"
	"strings"
)

// installSh is the Unix installer.
const installSh = "install.sh"

// installFacts: install.sh keeps the steps the tests that read it held.
func installFacts() Rule {
	return factRule(
		"install-facts",
		"install.sh dispatches on the OS, fails closed on an unknown one, runs every named step, and installs mise only from its verified release",
		[]string{installSh},
		installFactList,
	)
}

// installRequiredSteps is test_install_os_dispatch.py's REQUIRED_STEPS.
var installRequiredSteps = []string{
	"step_homebrew", "step_symlink_dotfiles", "step_sheldon", "step_brew_bundle",
	"step_gcloud_components", "step_corepack", "step_update_all",
}

var installFactList = []scriptFact{
	// tests/unit/test_install_zsh_steps.py
	fact("test_install_sh_runs_the_zsh_step", matches(installSh, `(?m)^step_zsh$`)),
	// tests/unit/test_install_os_dispatch.py
	fact("test_install_sh_identifies_dotfiles_os", pyMatches(installSh, `DOTFILES_OS\s*=\s*`)),
	fact("test_install_sh_dispatches_mac_linux_windows", installDispatchesEveryOS),
	fact("test_install_sh_fails_closed_on_unknown_os", pyMatches(installSh, `\*\)[\s\S]*?exit\s+[1-9][0-9]*`)),
	fact("test_install_sh_defines_required_step_function", installDefinesSteps(installRequiredSteps...)),
	fact("test_step_functions_are_called", installCallsSteps(installRequiredSteps...)),
	fact("test_install_sh_honours_legacy_skip_env_vars",
		has(installSh, "INSTALL_SKIP_HOMEBREW", "INSTALL_SKIP_GCLOUD", "INSTALL_SKIP_ADD_UPDATE")),
	fact("test_install_sh_enables_corepack_not_pnpm_globals",
		has(installSh, "corepack enable"),
		lacks(installSh, "step_pnpm_globals", "add-pnpm-g")),
	fact("test_install_sh_no_todo_windows_stub_remains", lacks(installSh, "_todo_windows")),
	fact("test_install_sh_windows_step_corepack_is_skipped", corepackSkipsWindows),
	fact("test_install_sh_skip_windows_calls_have_reason", skipWindowsCallsHaveReasons),
	// tests/unit/test_install_mise_bootstrap.py
	fact("test_defines_and_calls_mise_bootstrap",
		installDefinesSteps("step_mise_bootstrap"), installCallsSteps("step_mise_bootstrap")),
	fact("test_defines_and_calls_mise_install",
		installDefinesSteps("step_mise_install"), installCallsSteps("step_mise_install")),
	fact("test_mise_bootstrap_downloads_verified_binary", miseBootstrapVerifies),
	fact("test_mise_install_is_skippable", onInstallStep("step_mise_install", has(installSh, "INSTALL_SKIP_ADD_UPDATE"))),
	// tests/unit/test_wsl_clipboard.py
	fact("test_step_is_in_normal_install_flow", matches(installSh, `(?m)^step_wsl_clipboard$`)),
}

var (
	darwinArm   = pyCompile(`\bDarwin\)`)
	linuxArm    = pyCompile(`\bLinux\)`)
	windowsArm  = regexp.MustCompile(`MINGW\*\|MSYS\*\|CYGWIN\*\)|MSYS\*\|MINGW\*\|CYGWIN\*\)`)
	functionDef = pyCompile(`(?m)^[a-z_]+\s*\(\s*\)\s*\{[\s\S]*?^\}\s*$`).re
	skipWindows = pyCompile(`_skip_windows\s+"([^"]*)"\s+"([^"]*)"`).re
	corepackArm = regexp.MustCompile(`windows\)([\s\S]*?);;`)
	corepackWhy = regexp.MustCompile(`_skip_windows "step_corepack" "[^"]+"`)
)

// installDispatchesEveryOS: the case covers Darwin, Linux (each after a
// Python word boundary) and the MSYS family.
func installDispatchesEveryOS(files map[string]string) []string {
	text := files[installSh]
	var out []string
	if !darwinArm.Search(text) {
		out = append(out, "install.sh case must include a Darwin branch")
	}
	if !linuxArm.Search(text) {
		out = append(out, "install.sh case must include a Linux branch")
	}
	if !windowsArm.MatchString(text) {
		out = append(out, "install.sh case must include a Windows (MSYS/MINGW/Cygwin) branch")
	}
	return out
}

// installDefinesSteps: each step is a function definition at a line start.
func installDefinesSteps(steps ...string) factCheck {
	return func(files map[string]string) []string {
		var out []string
		for _, step := range steps {
			if !pyCompile(`(?m)^` + regexp.QuoteMeta(step) + `\s*\(\s*\)\s*\{`).Search(files[installSh]) {
				out = append(out, "install.sh must define a "+step+" function")
			}
		}
		return out
	}
}

// installCallsSteps: each step is named as a word in the body the
// function definitions leave (the tests' re.sub of them).
func installCallsSteps(steps ...string) factCheck {
	return func(files map[string]string) []string {
		body := functionDef.ReplaceAllString(files[installSh], "")
		var out []string
		for _, step := range steps {
			if !pyHasWord(body, step) {
				out = append(out, step+" is defined but never invoked")
			}
		}
		return out
	}
}

// onInstallStep runs checks over a step function's body (the tests'
// `^step\s*\(\s*\)\s*\{([\s\S]*?)^\}`, MULTILINE).
func onInstallStep(step string, checks ...factCheck) factCheck {
	body := pyCompile(`(?m)^` + regexp.QuoteMeta(step) + `\s*\(\s*\)\s*\{([\s\S]*?)^\}`).re
	return func(files map[string]string) []string {
		m := body.FindStringSubmatch(files[installSh])
		if m == nil {
			return []string{step + " definition not found"}
		}
		var out []string
		for _, c := range checks {
			for _, problem := range c(map[string]string{installSh: m[1]}) {
				out = append(out, problem+" (in "+step+")")
			}
		}
		return out
	}
}

// miseBootstrapVerifies: the bare-host download is mise's GitHub release,
// SHA256-checked, fetched with curl, never piped to a shell.
var miseBootstrapVerifies = onInstallStep("step_mise_bootstrap",
	has(installSh, "github.com/jdx/mise", "sha256sum -c", "curl"),
	lacks(installSh, "| bash", "| sh"))

// corepackSkipsWindows: step_corepack's windows arm skips with a reason and
// never enables corepack.
var corepackSkipsWindows = onInstallStep("step_corepack", func(files map[string]string) []string {
	m := corepackArm.FindStringSubmatch(files[installSh])
	if m == nil {
		return []string{"step_corepack has no windows) branch"}
	}
	var out []string
	if !corepackWhy.MatchString(m[1]) {
		out = append(out, "step_corepack windows) branch must skip with a reason")
	}
	if strings.Contains(m[1], "corepack enable") {
		out = append(out, "step_corepack windows) branch must not run corepack enable")
	}
	return out
})

// skipWindowsCallsHaveReasons: at least the seven skipped steps, each named
// step_* with a reason that is not blank.
func skipWindowsCallsHaveReasons(files map[string]string) []string {
	calls := skipWindows.FindAllStringSubmatch(files[installSh], -1)
	if len(calls) < 7 {
		return []string{fmt.Sprintf("expected at least 7 _skip_windows calls, found %d", len(calls))}
	}
	var out []string
	for _, c := range calls {
		if !strings.HasPrefix(c[1], "step_") {
			out = append(out, fmt.Sprintf("_skip_windows first argument must be a step name: %q", c[1]))
		}
		if pyStrip(c[2]) == "" {
			out = append(out, fmt.Sprintf("_skip_windows reason for %q is empty", c[1]))
		}
	}
	return out
}
