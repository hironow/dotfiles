package rules

import "testing"

const deployWiringFixture = `case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    ps_jev_marker_begin="# >>> dotfiles managed block: Jev launchers >>>"
    if grep -qF "$ps_jev_marker_begin" "$ps_profile"; then
      ps_profile_drop_block "$ps_profile" 'Jev launchers'
    fi
    printf 'function j-cc { }\nfunction j-pi { }\n' >> "$ps_profile"
    (export MISE_NODE_COREPACK=0 && run_agent_steps)
    exit 0
    ;;
esac
echo "==> Start to deploy dotfiles to home directory."
ensure_zprofile_login_path
mise -C / install
    run_agent_steps
`

func TestDeployWiringFacts(t *testing.T) {
	d := deployScriptPath
	runCases(t, deployWiringFacts(), func() Inputs { return Inputs{d: deployWiringFixture} }, []ruleCase{
		{"no login PATH on Unix", edit(d, "ensure_zprofile_login_path\n", ""), "test_unix_deploy_adds_the_block"},
		{"agent steps before mise installs", edit(d, "mise -C / install\n    run_agent_steps\n", "    run_agent_steps\nmise -C / install\n"), "test_unix_deploy_runs_the_steps_after_mise_installs"},
		{"the old launcher names", edit(d, "function j-cc { }", "function jev-claude { }"), "test_powershell_launchers_are_in_native_deploy"},
		{"corepack on for the agent steps", edit(d, "(export MISE_NODE_COREPACK=0 && run_agent_steps)", "run_agent_steps"), "test_powershell_launchers_are_in_native_deploy"},
		{"the Jev block is never refreshed", edit(d, "      ps_profile_drop_block \"$ps_profile\" 'Jev launchers'\n", "      :\n"), "test_the_native_deploy_refreshes_the_block_instead_of_skipping_it"},
	})
}

func TestEffectiveSettingsStdlib(t *testing.T) {
	c := effectiveSettingsChecker
	runCases(t, effectiveSettingsStdlib(), func() Inputs { return Inputs{c: "import json\n"} }, []ruleCase{
		{"claudelint is back", edit(c, "import json\n", "import json\nsubprocess.run(['bunx', 'claude-code-lint'])\n"), "test_effective_settings_checker_is_stdlib_only"},
	})
}

func TestQuintEvaluatorPinned(t *testing.T) {
	ok := `QUINT_EVALUATOR_REV="0123456789abcdef0123456789abcdef01234567"
QUINT_EVALUATOR_VERSION="v0.5.0"
cargo build --release --locked
cp target/release/quint_evaluator "${QUINT_HOME}/rust-evaluator-${QUINT_EVALUATOR_VERSION}/quint_evaluator"
`
	for _, c := range []struct {
		name, old, new string
		fails          bool
	}{
		{"pinned", "", "", false},
		{"a branch, not a commit", `"0123456789abcdef0123456789abcdef01234567"`, `"main"`, true},
		{"not a release tag", `"v0.5.0"`, `"0.5.0"`, true},
		{"no lockfile", "--locked", "", true},
	} {
		text := ok
		if c.old != "" {
			text = replaceOnce(text, c.old, c.new)
		}
		if got := quintEvaluatorPinned(map[string]string{featureInstall: text}); (len(got) > 0) != c.fails {
			t.Errorf("%s: %v", c.name, got)
		}
	}
}

func replaceOnce(s, old, new string) string {
	in := Inputs{"x": s}
	edit("x", old, new)(in)
	return in["x"].(string)
}
