package rules

import (
	"strings"
	"testing"
)

const installerFixture = `RUN apt-get install podman netavark aardvark-dns uidmap fuse-overlayfs
USER testuser
exec /usr/bin/podman "$@"
podman-provisioning-calls
ARG DOTFILES_INSTALL_ACCEPTANCE_RUN
RUN test -n "$DOTFILES_INSTALL_ACCEPTANCE_RUN" && bash /tmp/dotfiles-repo/install.sh
printf 'DOTFILES_INSTALL_PASS1:%s\n' "$DOTFILES_INSTALL_ACCEPTANCE_RUN"
RUN bash /tmp/dotfiles-repo/install.sh
printf 'DOTFILES_INSTALL_PASS2:%s\n' "$DOTFILES_INSTALL_ACCEPTANCE_RUN"
test "$(wc -l
test "$(sort -u
printf 'DOTFILES_INSTALL_TRIPWIRE:%s\n' "$DOTFILES_INSTALL_ACCEPTANCE_RUN"
`

func TestInstallerAcceptanceFacts(t *testing.T) {
	p := installerDockerfile
	runAcceptanceCases(t, installerAcceptanceFacts(), func() Inputs { return Inputs{p: installerFixture} }, []ruleCase{
		{"sudo grant", edit(p, "USER testuser", "RUN echo NOPASSWD\nUSER testuser"), "test_installer_image_provisions_native_podman_before_nonroot_setup"},
		{"late package", edit(p, "uidmap fuse-overlayfs\nUSER testuser", "uidmap\nUSER testuser\nfuse-overlayfs"), "test_installer_image_provisions_native_podman_before_nonroot_setup"},
		{"one install", edit(p, "RUN bash /tmp/dotfiles-repo/install.sh", "RUN true"), "test_installer_image_provisions_native_podman_before_nonroot_setup"},
		{"early nonce", edit(p, "USER testuser", "ARG DOTFILES_INSTALL_ACCEPTANCE_RUN\nUSER testuser"), "test_installer_image_busts_only_setup_cache_and_emits_run_bound_evidence"},
		{"no nonce check", edit(p, `test -n "$DOTFILES_INSTALL_ACCEPTANCE_RUN"`, "true"), "test_installer_image_busts_only_setup_cache_and_emits_run_bound_evidence"},
		{"late count", edit(p, `test "$(wc -l`, "true"), "test_installer_image_busts_only_setup_cache_and_emits_run_bound_evidence"},
		{"no second marker", edit(p, "DOTFILES_INSTALL_PASS2:%s", "PASS2"), "test_installer_image_busts_only_setup_cache_and_emits_run_bound_evidence"},
		{"CRLF", edit(p, "\n", "\r\n"), ""},
	})
}

const psProfileFixture = `ps_profile_lib.sh
resolve_ps_profile
ps_profile_legacy
win-profile-legacy
sed -i '/# >>> dotfiles managed block: Jev launchers >>>/d'
`

func TestPSProfileFacts(t *testing.T) {
	base := func() Inputs {
		return Inputs{deployScriptPath: psProfileFixture, cleanScriptPath: psProfileFixture, doctorScript: psProfileFixture}
	}
	cases := []ruleCase{
		{"no legacy sweep", edit(cleanScriptPath, "ps_profile_legacy", ""), "test_clean_also_sweeps_legacy_profile"},
		{"no legacy warning", edit(doctorScript, "win-profile-legacy", ""), "test_doctor_warns_on_stale_legacy_blocks"},
		{"missing Jev removal", edit(cleanScriptPath, "Jev launchers", "Jev"), "test_clean_removes_every_block_deploy_writes"},
		{"empty written set", edit(deployScriptPath, "# >>> dotfiles managed block:", "# other:"), "test_clean_removes_every_block_deploy_writes"},
		{"untrimmed capture", edit(cleanScriptPath, "Jev launchers >>>", "Jev launchers  >>>"), "test_clean_removes_every_block_deploy_writes"},
		{"Unicode strip and splitlines", edit(cleanScriptPath, "sed -i", "\u0085\u2003sed -i"), ""},
	}
	for _, p := range []string{deployScriptPath, cleanScriptPath, doctorScript} {
		cases = append(cases,
			ruleCase{p + " unresolved", edit(p, "resolve_ps_profile", ""), "test_scripts_resolve_profile_instead_of_hardcoding"},
			ruleCase{p + " hardcoded", edit(p, "ps_profile_lib.sh", `ps_profile="$HOME/Documents/PowerShell`), "test_scripts_resolve_profile_instead_of_hardcoding"})
	}
	runAcceptanceCases(t, psProfileFacts(), base, cases)
}

func TestZshStartupFacts(t *testing.T) {
	base := func() Inputs {
		return Inputs{zshrcPath: "# DOCKER_HOST= is only a comment\nexport PODMAN_COMPOSE_PROVIDER=podman-compose\nzle -N _ctrl_enter_newline\nbindkey '^[[13;5u' _ctrl_enter_newline\n"}
	}
	runAcceptanceCases(t, zshStartupFacts(), base, []ruleCase{
		{"engine probe", edit(zshrcPath, "export PODMAN", "podman machine inspect\nexport PODMAN"), "test_shell_selects_the_provider_without_probing_or_redirecting_engines"},
		{"no provider", edit(zshrcPath, "=podman-compose", "=other"), "test_shell_selects_the_provider_without_probing_or_redirecting_engines"},
		{"first occurrence wins", edit(zshrcPath, "# DOCKER_HOST= is only a comment", "# bindkey '^[[13;5u'"), "test_the_widget_exists_before_it_is_bound"},
		{"no registration", edit(zshrcPath, "zle -N", "zle -X"), "test_the_widget_exists_before_it_is_bound"},
		{"Unicode comment and CR", edit(zshrcPath, "# DOCKER_HOST= is only a comment\n", "\u2003# DOCKER_HOST=\r"), ""},
	})
}

const tmuxKeyFixture = "# xterm-keys extended-keys-format\nset -s extended-keys always\nset -as terminal-features 'xterm*:extkeys'\n"

func TestTmuxKeyFacts(t *testing.T) {
	p := tmuxConfPath
	runAcceptanceCases(t, tmuxKeyFacts(), func() Inputs { return Inputs{p: tmuxKeyFixture} }, []ruleCase{
		{"not forced", edit(p, "always", "on"), "test_tmux_forces_extended_keys_for_clients_that_never_asked"},
		{"duplicate command", edit(p, "set -s extended-keys always", "set -s extended-keys always\nset -s extended-keys always"), "test_tmux_forces_extended_keys_for_clients_that_never_asked"},
		{"redundant option", edit(p, "# xterm-keys", "set -w xterm-keys"), "test_tmux_does_not_add_xterm_keys_or_switch_the_format"},
		{"format", edit(p, "# xterm-keys", "set -s extended-keys-format"), "test_tmux_does_not_add_xterm_keys_or_switch_the_format"},
		{"Unicode lines and whitespace", edit(p, "\nset -s", "\u0085\u001cset -s"), ""},
	})
}

func TestBrewfileJQUsesPythonRegex(t *testing.T) {
	for _, c := range []struct {
		text  string
		fails bool
	}{
		{"brew \"podman\"", false},
		{"# brew 'jq'", false},
		{"  brew('jq')", true},
		{"\u2003brew\n(\u001c\"jq'", true},
		{"brew 'jq-extra'", false},
	} {
		in := Inputs{doctorScript: doctorFixture2, macBrewfile: brewfileFixture + "\n" + c.text}
		found := false
		for _, f := range brewfileDockerFree().Check(in) {
			found = found || strings.Contains(f.Message, "test_mac_homebrew_restore_does_not_reinstall_mise_jq")
		}
		if found != c.fails {
			t.Errorf("%q: found %v", c.text, found)
		}
	}
}

func runAcceptanceCases(t *testing.T, rule Rule, base func() Inputs, cases []ruleCase) {
	t.Helper()
	for _, c := range cases {
		if c.expect != "" {
			runCases(t, rule, base, []ruleCase{c})
			continue
		}
		t.Run(c.name, func(t *testing.T) {
			in := base()
			c.change(in)
			if got := rule.Check(in); len(got) != 0 {
				t.Fatalf("accepted input: %v", got)
			}
		})
	}
}
