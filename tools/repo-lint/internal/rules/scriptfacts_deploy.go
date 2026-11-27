package rules

import "strings"

// deployUnixStart opens deploy.sh's Unix part; the tests split there.
const deployUnixStart = `echo "==> Start to deploy dotfiles to home directory."`

// deployWiringFacts: deploy wires the login PATH and the agent steps on
// Unix, and the Jev launchers on native Windows.
func deployWiringFacts() Rule {
	return factRule(
		"deploy-wiring-facts",
		"deploy runs its steps where and when they need to run: the login PATH and agent steps on Unix, the Jev launchers on native Windows",
		[]string{deployScriptPath},
		[]scriptFact{
			// tests/unit/test_deploy_zprofile.py
			fact("test_unix_deploy_adds_the_block", onDeployUnix(has(deployScriptPath, "ensure_zprofile_login_path"))),
			// tests/unit/test_deploy_pi_extensions.py
			fact("test_unix_deploy_runs_the_steps_after_mise_installs",
				onDeployUnix(has(deployScriptPath, "mise -C / install"), order(deployScriptPath, "mise -C / install", "    run_agent_steps\n"))),
			// tests/unit/test_jev_powershell.py
			fact("test_powershell_launchers_are_in_native_deploy",
				onDeployWindows(
					has(deployScriptPath,
						`ps_jev_marker_begin="# >>> dotfiles managed block: Jev launchers >>>"`,
						"(export MISE_NODE_COREPACK=0 && run_agent_steps)",
						"function j-cc", "function j-pi"),
					lacks(deployScriptPath, "function jev-claude", "function jev-pi"))),
			fact("test_the_native_deploy_refreshes_the_block_instead_of_skipping_it",
				onDeployWindows(has(deployScriptPath, `ps_profile_drop_block "$ps_profile" 'Jev launchers'`))),
		},
	)
}

// onDeployUnix runs checks over the text after the Unix marker (the tests'
// DEPLOY.split(marker, 1)[1], which fails when the marker is missing).
func onDeployUnix(checks ...factCheck) factCheck {
	return func(files map[string]string) []string {
		_, unix, ok := strings.Cut(files[deployScriptPath], deployUnixStart)
		if !ok {
			return []string{deployScriptPath + " lost its Unix part's start line"}
		}
		return runOn(deployScriptPath, unix, checks)
	}
}

// onDeployWindows runs checks over the text before the first `    exit 0`
// (the tests' DEPLOY.split("    exit 0", 1)[0], the whole file when it is
// missing).
func onDeployWindows(checks ...factCheck) factCheck {
	return func(files map[string]string) []string {
		windows, _, _ := strings.Cut(files[deployScriptPath], "    exit 0")
		return runOn(deployScriptPath, windows, checks)
	}
}

// runOn runs checks with path's text replaced by part.
func runOn(path, part string, checks []factCheck) []string {
	var out []string
	for _, c := range checks {
		out = append(out, c(map[string]string{path: part})...)
	}
	return out
}

// effectiveSettingsChecker validates the composed Claude settings.
const effectiveSettingsChecker = "scripts/check_effective_settings.py"

// effectiveSettingsStdlib: the settings check is the repository's own
// stdlib code, never the retired third-party claudelint (ADR-0041).
func effectiveSettingsStdlib() Rule {
	return factRule(
		"effective-settings-stdlib",
		"the composed settings are checked by in-repo stdlib code, not the retired third-party claudelint (ADR-0041)",
		[]string{effectiveSettingsChecker},
		[]scriptFact{
			// tests/unit/test_no_third_party_claudelint.py
			fact("test_effective_settings_checker_is_stdlib_only", lacks(effectiveSettingsChecker, "claude-code-lint", "bunx")),
		},
	)
}
