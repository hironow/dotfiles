package rules

import (
	"fmt"
	"regexp"
	"strings"
)

const (
	installerDockerfile = "tests/docker/InstallTest.Dockerfile"
	cleanScriptPath     = "scripts/clean.sh"
	tmuxConfPath        = "tools/tmux/tmux.conf"
	installerCall       = "bash /tmp/dotfiles-repo/install.sh"
	acceptanceNonce     = "DOTFILES_INSTALL_ACCEPTANCE_RUN"
)

func installerAcceptanceFacts() Rule {
	return factRule("installer-acceptance-facts", "installer acceptance provisions native Podman and binds both unprivileged passes to fresh evidence",
		[]string{installerDockerfile}, []scriptFact{
			// tests/unit/test_cli_release_age_policy.py
			fact("test_installer_image_provisions_native_podman_before_nonroot_setup", installerProvisions),
			fact("test_installer_image_busts_only_setup_cache_and_emits_run_bound_evidence", installerEvidence),
		})
}

func installerProvisions(files map[string]string) []string {
	p := installerDockerfile
	root, _, _ := strings.Cut(files[p], "USER testuser")
	out := runOn(p, root, []factCheck{has(p, "podman", "netavark", "aardvark-dns", "uidmap", "fuse-overlayfs")})
	out = append(out, lacks(p, "NOPASSWD")(files)...)
	out = append(out, has(p, "podman-provisioning-calls", `exec /usr/bin/podman "$@"`)(files)...)
	if strings.Count(files[p], installerCall) != 2 {
		out = append(out, "exactly two installer calls are required")
	}
	return out
}

func installerEvidence(files map[string]string) []string {
	p, text := installerDockerfile, files[installerDockerfile]
	first := strings.Index(text, installerCall)
	if first < 0 {
		return []string{"first installer call is missing"}
	}
	second := strings.Index(text[first+1:], installerCall)
	if second < 0 {
		return []string{"second installer call is missing"}
	}
	second += first + 1
	out := order(p, "USER testuser", "ARG "+acceptanceNonce)(files)
	out = append(out, order(p, "ARG "+acceptanceNonce, installerCall)(files)...)
	out = append(out, runOn(p, text[:first], []factCheck{has(p, `test -n "$`+acceptanceNonce+`"`)})...)
	pass1, pass2, final := strings.Index(text, "DOTFILES_INSTALL_PASS1:%s"), strings.Index(text, "DOTFILES_INSTALL_PASS2:%s"), strings.Index(text, "DOTFILES_INSTALL_TRIPWIRE:%s")
	if first >= pass1 || pass1 >= second || second >= pass2 || pass2 >= final {
		out = append(out, "installer calls and PASS1/PASS2/TRIPWIRE must stay in order")
	}
	for _, anchor := range []string{`test "$(wc -l`, `test "$(sort -u`} {
		at := strings.Index(text, anchor)
		if at < 0 || final < 0 || at >= final {
			out = append(out, "tripwire must follow "+anchor)
		}
	}
	for _, marker := range []string{"PASS1", "PASS2", "TRIPWIRE"} {
		out = append(out, has(p, "printf 'DOTFILES_INSTALL_"+marker+":%s\\n' \"$"+acceptanceNonce+"\"")(files)...)
	}
	return out
}

func psProfileFacts() Rule {
	return factRule("ps-profile-facts", "deploy, clean and doctor resolve PowerShell profiles and account for legacy managed blocks",
		[]string{deployScriptPath, cleanScriptPath, doctorScript}, []scriptFact{
			// tests/unit/test_ps_profile_path.py
			fact("test_scripts_resolve_profile_instead_of_hardcoding", profileResolution),
			fact("test_clean_also_sweeps_legacy_profile", has(cleanScriptPath, "ps_profile_legacy")),
			fact("test_doctor_warns_on_stale_legacy_blocks", has(doctorScript, "ps_profile_legacy", "win-profile-legacy")),
			fact("test_clean_removes_every_block_deploy_writes", profileBlockRemovals),
		})
}

func profileResolution(files map[string]string) []string {
	var out []string
	for _, p := range []string{deployScriptPath, cleanScriptPath, doctorScript} {
		out = append(out, has(p, "ps_profile_lib.sh", "resolve_ps_profile")(files)...)
		out = append(out, lacks(p, `ps_profile="$HOME/Documents/PowerShell`)(files)...)
	}
	return out
}

var profileBlockMarker = regexp.MustCompile(`# >>> dotfiles managed block: ([^>]+?) >>>`)

func profileBlockRemovals(files map[string]string) []string {
	written := profileBlockMarker.FindAllStringSubmatch(files[deployScriptPath], -1)
	if len(written) == 0 {
		return []string{"deploy.sh writes no managed blocks"}
	}
	removed := map[string]bool{}
	for _, line := range pySplitlines(files[cleanScriptPath]) {
		if strings.HasPrefix(pyStrip(line), "sed -i") {
			for _, m := range profileBlockMarker.FindAllStringSubmatch(line, -1) {
				removed[m[1]] = true
			}
		}
	}
	var out []string
	for _, m := range written {
		if !removed[m[1]] {
			out = append(out, fmt.Sprintf("clean.sh never removes %q", m[1]))
		}
	}
	return out
}

func zshStartupFacts() Rule {
	return factRule("zsh-startup-facts", "shell startup selects the Compose provider and registers the newline widget before binding it",
		[]string{zshrcPath}, []scriptFact{
			// tests/unit/test_cli_release_age_policy.py
			fact("test_shell_selects_the_provider_without_probing_or_redirecting_engines", func(files map[string]string) []string {
				return runOn(zshrcPath, strings.Join(pyCodeLines(files[zshrcPath]), "\n"), []factCheck{
					has(zshrcPath, "PODMAN_COMPOSE_PROVIDER=podman-compose"),
					lacks(zshrcPath, "podman machine inspect", "DOCKER_HOST=", ".orbstack", ".docker/completions"),
				})
			}),
			// tests/unit/test_zshrc_ctrl_enter.py
			fact("test_the_widget_exists_before_it_is_bound", order(zshrcPath, "zle -N _ctrl_enter_newline", "bindkey '^[[13;5u'")),
		})
}

func tmuxKeyFacts() Rule {
	return factRule("tmux-key-facts", "tmux forwards extended keys and keeps the default key format without redundant options",
		[]string{tmuxConfPath}, []scriptFact{
			// tests/unit/test_terminal_word_movement.py
			fact("test_tmux_forces_extended_keys_for_clients_that_never_asked", func(files map[string]string) []string {
				lines := tmuxCommandLines(files[tmuxConfPath])
				var out []string
				for _, command := range []string{"set -s extended-keys always", "set -as terminal-features 'xterm*:extkeys'"} {
					count := 0
					for _, line := range lines {
						if line == command {
							count++
						}
					}
					if count != 1 {
						out = append(out, "exactly one command is required: "+command)
					}
				}
				return out
			}),
			fact("test_tmux_does_not_add_xterm_keys_or_switch_the_format", func(files map[string]string) []string {
				return runOn(tmuxConfPath, strings.Join(tmuxCommandLines(files[tmuxConfPath]), "\n"), []factCheck{lacks(tmuxConfPath, "xterm-keys", "extended-keys-format")})
			}),
		})
}

func tmuxCommandLines(text string) []string {
	var out []string
	for _, line := range pyCodeLines(text) {
		if line = pyStrip(line); line != "" {
			out = append(out, line)
		}
	}
	return out
}
